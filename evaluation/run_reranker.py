"""Run production reranker_v0.1 over frozen component candidate unions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.reranker_retrieval import (
    BATCH_SIZE,
    CANDIDATE_DEPTH,
    CANDIDATE_POOL_VERSION,
    MAX_LENGTH,
    MODEL_FILE_SHA256,
    MODEL_ID,
    MODEL_REVISION,
    OUTPUT_DEPTH,
    SEED,
    TORCH_NUM_INTEROP_THREADS,
    TORCH_NUM_THREADS,
    TransformerCrossEncoder,
    add_hybrid_ranks,
    build_candidate_union,
    rank_scored_candidates,
    sha256_file,
    stable_json_line,
    truncation_diagnostics,
    validate_artifact_hash,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BM25_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1.jsonl"
DEFAULT_EMBEDDING_PATH = ROOT / "evaluation" / "results" / "embedding_v0.1.jsonl"
DEFAULT_HYBRID_PATH = ROOT / "evaluation" / "results" / "hybrid_v0.1.jsonl"
DEFAULT_QUERY_PATH = ROOT / "benchmark" / "retrieval_queries_v0.1.csv"
DEFAULT_OUTPUT_PATH = ROOT / "evaluation" / "results" / "reranker_v0.1.jsonl"
DEFAULT_MODEL_CACHE_DIR = ROOT / "data" / "model_cache" / "huggingface"

BM25_VERSION = "bm25_v0.1"
BM25_INPUT_SHA256 = "7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1"
EMBEDDING_VERSION = "embedding_v0.1"
EMBEDDING_INPUT_SHA256 = "d997bb8ac72ba2e003eea440b0e805e3dd9722b053874162bee7d6754bc2bfa3"
HYBRID_VERSION = "hybrid_v0.1"
HYBRID_INPUT_SHA256 = "17f2f07fd24163b443dd3909aaa81fd188a8dbef77786532d7eb432094769846"
RETRIEVAL_QUERY_VERSION = "retrieval_queries_v0.1.1"
RETRIEVAL_QUERY_SHA256 = "4de3208bf457e0670d691e95284c5675006c825be85a2dca159e6f5268a61c1c"
CORPUS_FINGERPRINT = "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
EXPECTED_QUERY_COUNT = 16
RETRIEVAL_METHOD = "reranker_v0.1"


def _load_queries(path: Path) -> list[dict[str, str]]:
    validate_artifact_hash(path, RETRIEVAL_QUERY_SHA256)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["q_id", "query_en"]:
            raise ValueError(
                "frozen retrieval query file must contain exactly q_id,query_en; "
                f"got {reader.fieldnames}"
            )
        queries = [dict(row) for row in reader]
    q_ids = [query["q_id"] for query in queries]
    if len(queries) != EXPECTED_QUERY_COUNT:
        raise ValueError(
            f"expected {EXPECTED_QUERY_COUNT} frozen queries; got {len(queries)}"
        )
    if any(not q_id for q_id in q_ids) or len(set(q_ids)) != len(q_ids):
        raise ValueError("frozen query q_id values must be non-empty and unique")
    if any(not query["query_en"] for query in queries):
        raise ValueError("frozen query text must be non-empty")
    return queries


def _load_jsonl(path: Path, *, expected_sha256: str) -> list[dict[str, Any]]:
    validate_artifact_hash(path, expected_sha256)
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
            if not isinstance(record, dict):
                raise ValueError(f"JSON record at {path}:{line_number} must be an object")
            records.append(record)
    return records


def _index_records(
    records: Sequence[dict[str, Any]],
    *,
    component: str,
    expected_method: str,
) -> dict[str, dict[str, Any]]:
    if len(records) != EXPECTED_QUERY_COUNT:
        raise ValueError(
            f"expected {EXPECTED_QUERY_COUNT} {component} records; got {len(records)}"
        )
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        q_id = record.get("q_id")
        if not isinstance(q_id, str) or not q_id:
            raise ValueError(f"{component} record requires q_id")
        if q_id in indexed:
            raise ValueError(f"duplicate {component} q_id: {q_id}")
        if record.get("retrieval_method") != expected_method:
            raise ValueError(f"unexpected {component} retrieval_method for {q_id}")
        if record.get("corpus_fingerprint") != CORPUS_FINGERPRINT:
            raise ValueError(f"unexpected {component} corpus fingerprint for {q_id}")
        indexed[q_id] = record
    return indexed


def _write_jsonl_atomic(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(stable_json_line(record))
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _length_summary(values: Sequence[int]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "min": 0, "median": 0.0, "max": 0}
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    median = (
        float(ordered[midpoint])
        if len(ordered) % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
    )
    return {"count": len(values), "min": min(values), "median": median, "max": max(values)}


def run(
    *,
    bm25_path: Path = DEFAULT_BM25_PATH,
    embedding_path: Path = DEFAULT_EMBEDDING_PATH,
    hybrid_path: Path | None = DEFAULT_HYBRID_PATH,
    query_path: Path = DEFAULT_QUERY_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    model_cache_dir: Path = DEFAULT_MODEL_CACHE_DIR,
    local_files_only: bool = False,
) -> dict[str, Any]:
    """Validate inputs, score every union candidate, and emit top 50."""
    queries = _load_queries(query_path)
    bm25_records = _load_jsonl(bm25_path, expected_sha256=BM25_INPUT_SHA256)
    embedding_records = _load_jsonl(
        embedding_path,
        expected_sha256=EMBEDDING_INPUT_SHA256,
    )
    hybrid_records = (
        None
        if hybrid_path is None
        else _load_jsonl(hybrid_path, expected_sha256=HYBRID_INPUT_SHA256)
    )
    bm25_by_q_id = _index_records(
        bm25_records,
        component="BM25",
        expected_method="bm25",
    )
    embedding_by_q_id = _index_records(
        embedding_records,
        component="embedding",
        expected_method=EMBEDDING_VERSION,
    )
    hybrid_by_q_id = (
        {}
        if hybrid_records is None
        else _index_records(
            hybrid_records,
            component="hybrid",
            expected_method=HYBRID_VERSION,
        )
    )
    query_ids = {query["q_id"] for query in queries}
    if set(bm25_by_q_id) != query_ids or set(embedding_by_q_id) != query_ids:
        raise ValueError("component q_id sets must exactly match frozen queries")
    if hybrid_records is not None and set(hybrid_by_q_id) != query_ids:
        raise ValueError("hybrid q_id set must exactly match frozen queries")
    for record in embedding_records:
        if record.get("model_id") != "BAAI/bge-base-en-v1.5":
            raise ValueError(f"unexpected embedding model for {record.get('q_id')}")
        if record.get("model_revision") != "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a":
            raise ValueError(
                f"unexpected embedding model revision for {record.get('q_id')}"
            )

    scorer = TransformerCrossEncoder(
        cache_dir=model_cache_dir,
        local_files_only=local_files_only,
    )
    output_records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    all_original_lengths: list[int] = []
    all_retained_lengths: list[int] = []
    all_truncated_count = 0

    for query in queries:
        q_id = query["q_id"]
        query_en = query["query_en"]
        bm25_record = bm25_by_q_id[q_id]
        embedding_record = embedding_by_q_id[q_id]
        if bm25_record.get("query_en") != query_en:
            raise ValueError(f"BM25 query text mismatch for {q_id}")
        if embedding_record.get("query_en") != query_en:
            raise ValueError(f"embedding query text mismatch for {q_id}")
        union = build_candidate_union(
            bm25_record,
            embedding_record,
            expected_depth=CANDIDATE_DEPTH,
        )
        union = add_hybrid_ranks(
            union,
            hybrid_by_q_id.get(q_id),
            q_id=q_id,
            query_en=query_en,
            corpus_fingerprint=CORPUS_FINGERPRINT,
        )
        pair_scores = scorer.score_candidates(query_en, union)
        ranked_results = rank_scored_candidates(
            union,
            pair_scores,
            top_k=OUTPUT_DEPTH,
        )
        if len(ranked_results) != OUTPUT_DEPTH:
            raise ValueError(f"expected {OUTPUT_DEPTH} reranked results for {q_id}")
        result_ids = [result["chunk_id"] for result in ranked_results]
        if len(result_ids) != len(set(result_ids)):
            raise AssertionError(f"duplicate reranker output chunk_id for {q_id}")
        union_ids = {candidate["chunk_id"] for candidate in union}
        if not set(result_ids) <= union_ids:
            raise AssertionError(f"reranker output outside frozen union for {q_id}")

        bm25_ids = {result["chunk_id"] for result in bm25_record["ranked_results"]}
        embedding_ids = {
            result["chunk_id"] for result in embedding_record["ranked_results"]
        }
        token_diagnostics = truncation_diagnostics(pair_scores)
        question_diagnostics = {
            "q_id": q_id,
            "candidate_union_count": len(union),
            "overlap_count": len(bm25_ids & embedding_ids),
            **token_diagnostics,
            "final_output_count": len(ranked_results),
        }
        diagnostics.append(question_diagnostics)
        all_original_lengths.extend(score.original_token_count for score in pair_scores)
        all_retained_lengths.extend(score.retained_token_count for score in pair_scores)
        all_truncated_count += token_diagnostics["truncated_pair_count"]

        output_records.append(
            {
                "q_id": q_id,
                "query_en": query_en,
                "retrieval_method": RETRIEVAL_METHOD,
                "candidate_pool": {
                    "version": CANDIDATE_POOL_VERSION,
                    "definition": "frozen bm25_v0.1 top50 UNION frozen embedding_v0.1 top50",
                    "deduplication_key": "chunk_id",
                    "bm25_depth": CANDIDATE_DEPTH,
                    "embedding_depth": CANDIDATE_DEPTH,
                },
                "bm25_input_artifact_sha256": BM25_INPUT_SHA256,
                "embedding_input_artifact_sha256": EMBEDDING_INPUT_SHA256,
                "hybrid_input_artifact_sha256": (
                    HYBRID_INPUT_SHA256 if hybrid_records is not None else None
                ),
                "retrieval_query_version": RETRIEVAL_QUERY_VERSION,
                "retrieval_query_sha256": RETRIEVAL_QUERY_SHA256,
                "corpus_fingerprint": CORPUS_FINGERPRINT,
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "model_file_sha256": MODEL_FILE_SHA256,
                "max_length": MAX_LENGTH,
                "runtime_config": dict(scorer.runtime_config),
                "diagnostics": question_diagnostics,
                "ranked_results": ranked_results,
            }
        )

    _write_jsonl_atomic(output_path, output_records)
    total_pairs = sum(item["input_pair_count"] for item in diagnostics)
    return {
        "artifact_sha256": sha256_file(output_path),
        "output_path": str(output_path),
        "query_count": len(output_records),
        "final_result_count": sum(
            len(record["ranked_results"]) for record in output_records
        ),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "candidate_pool_version": CANDIDATE_POOL_VERSION,
        "runtime_config": dict(scorer.runtime_config),
        "diagnostics": diagnostics,
        "aggregate_diagnostics": {
            "question_count": len(diagnostics),
            "total_candidate_union_count": sum(
                item["candidate_union_count"] for item in diagnostics
            ),
            "total_overlap_count": sum(item["overlap_count"] for item in diagnostics),
            "input_pair_count": total_pairs,
            "truncated_pair_count": all_truncated_count,
            "truncated_pair_proportion": (
                0.0 if total_pairs == 0 else all_truncated_count / total_pairs
            ),
            "original_token_count": _length_summary(all_original_lengths),
            "retained_token_count": _length_summary(all_retained_lengths),
            "final_output_count": sum(
                item["final_output_count"] for item in diagnostics
            ),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bm25", type=Path, default=DEFAULT_BM25_PATH)
    parser.add_argument("--embedding", type=Path, default=DEFAULT_EMBEDDING_PATH)
    parser.add_argument("--hybrid", type=Path, default=DEFAULT_HYBRID_PATH)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--model-cache-dir", type=Path, default=DEFAULT_MODEL_CACHE_DIR)
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="require the pinned model snapshot to be present in model-cache-dir",
    )
    args = parser.parse_args(argv)
    summary = run(
        bm25_path=args.bm25,
        embedding_path=args.embedding,
        hybrid_path=args.hybrid,
        query_path=args.queries,
        output_path=args.output,
        model_cache_dir=args.model_cache_dir,
        local_files_only=args.local_files_only,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
