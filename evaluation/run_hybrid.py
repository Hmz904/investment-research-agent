"""Fuse the frozen BM25 and embedding artifacts without gold judgments."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from src.hybrid_retrieval import (
    reciprocal_rank_fusion,
    sha256_file,
    stable_json_line,
    validate_artifact_hash,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BM25_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1.jsonl"
DEFAULT_EMBEDDING_PATH = ROOT / "evaluation" / "results" / "embedding_v0.1.jsonl"
DEFAULT_QUERY_PATH = ROOT / "benchmark" / "retrieval_queries_v0.1.csv"
DEFAULT_OUTPUT_PATH = ROOT / "evaluation" / "results" / "hybrid_v0.1.jsonl"

BM25_VERSION = "bm25_v0.1"
BM25_INPUT_SHA256 = "7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1"
EMBEDDING_VERSION = "embedding_v0.1"
EMBEDDING_INPUT_SHA256 = "d997bb8ac72ba2e003eea440b0e805e3dd9722b053874162bee7d6754bc2bfa3"
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBEDDING_MODEL_REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
RETRIEVAL_QUERY_VERSION = "retrieval_queries_v0.1.1"
RETRIEVAL_QUERY_SHA256 = "4de3208bf457e0670d691e95284c5675006c825be85a2dca159e6f5268a61c1c"
CORPUS_FINGERPRINT = "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
RETRIEVAL_METHOD = "hybrid_v0.1"
FUSION_METHOD = "reciprocal_rank_fusion"
EXPECTED_QUERY_COUNT = 16
CANDIDATE_DEPTH = 50
RRF_K = 60
TOP_K = 50


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


def _index_and_validate_records(
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
            raise ValueError(
                f"unexpected {component} retrieval_method for {q_id}: "
                f"{record.get('retrieval_method')!r}"
            )
        if record.get("corpus_fingerprint") != CORPUS_FINGERPRINT:
            raise ValueError(f"unexpected {component} corpus fingerprint for {q_id}")
        ranked_results = record.get("ranked_results")
        if not isinstance(ranked_results, list) or len(ranked_results) != CANDIDATE_DEPTH:
            count = len(ranked_results) if isinstance(ranked_results, list) else None
            raise ValueError(
                f"expected {CANDIDATE_DEPTH} {component} candidates for {q_id}; "
                f"got {count}"
            )
        chunk_ids: set[str] = set()
        for position, result in enumerate(ranked_results, start=1):
            if not isinstance(result, dict) or result.get("rank") != position:
                raise ValueError(
                    f"invalid {component} rank at {q_id} position {position}"
                )
            chunk_id = result.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValueError(
                    f"missing {component} chunk_id at {q_id} position {position}"
                )
            if chunk_id in chunk_ids:
                raise ValueError(f"duplicate {component} chunk_id for {q_id}: {chunk_id}")
            chunk_ids.add(chunk_id)
        indexed[q_id] = record
    return indexed


def _validate_embedding_binding(records: Sequence[dict[str, Any]]) -> None:
    for record in records:
        q_id = record.get("q_id")
        if record.get("model_id") != EMBEDDING_MODEL:
            raise ValueError(f"unexpected embedding model for {q_id}")
        if record.get("model_revision") != EMBEDDING_MODEL_REVISION:
            raise ValueError(f"unexpected embedding model revision for {q_id}")


def _write_jsonl_atomic(path: Path, records: Sequence[dict[str, Any]]) -> None:
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


def run(
    *,
    bm25_path: Path = DEFAULT_BM25_PATH,
    embedding_path: Path = DEFAULT_EMBEDDING_PATH,
    query_path: Path = DEFAULT_QUERY_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    queries = _load_queries(query_path)
    bm25_records = _load_jsonl(bm25_path, expected_sha256=BM25_INPUT_SHA256)
    embedding_records = _load_jsonl(
        embedding_path,
        expected_sha256=EMBEDDING_INPUT_SHA256,
    )
    bm25_by_q_id = _index_and_validate_records(
        bm25_records,
        component="BM25",
        expected_method="bm25",
    )
    embedding_by_q_id = _index_and_validate_records(
        embedding_records,
        component="embedding",
        expected_method=EMBEDDING_VERSION,
    )
    _validate_embedding_binding(embedding_records)

    query_ids = {query["q_id"] for query in queries}
    if set(bm25_by_q_id) != query_ids or set(embedding_by_q_id) != query_ids:
        raise ValueError("component q_id sets must exactly match the frozen queries")

    output_records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for query in queries:
        q_id = query["q_id"]
        query_en = query["query_en"]
        bm25_record = bm25_by_q_id[q_id]
        embedding_record = embedding_by_q_id[q_id]
        if bm25_record.get("query_en") != query_en:
            raise ValueError(f"BM25 query text mismatch for {q_id}")
        if embedding_record.get("query_en") != query_en:
            raise ValueError(f"embedding query text mismatch for {q_id}")
        if bm25_record["corpus_fingerprint"] != embedding_record["corpus_fingerprint"]:
            raise ValueError(f"component corpus fingerprints disagree for {q_id}")

        ranked_results = reciprocal_rank_fusion(
            bm25_record,
            embedding_record,
            rrf_k=RRF_K,
            top_k=TOP_K,
        )
        output_records.append(
            {
                "q_id": q_id,
                "query_en": query_en,
                "retrieval_method": RETRIEVAL_METHOD,
                "fusion_method": FUSION_METHOD,
                "rrf_k": RRF_K,
                "component_weights": {"bm25": 1.0, "embedding": 1.0},
                "candidate_depth": {
                    "bm25": CANDIDATE_DEPTH,
                    "embedding": CANDIDATE_DEPTH,
                },
                "bm25_version": BM25_VERSION,
                "bm25_input_artifact_sha256": BM25_INPUT_SHA256,
                "embedding_version": EMBEDDING_VERSION,
                "embedding_input_artifact_sha256": EMBEDDING_INPUT_SHA256,
                "embedding_model": EMBEDDING_MODEL,
                "embedding_model_revision": EMBEDDING_MODEL_REVISION,
                "retrieval_query_version": RETRIEVAL_QUERY_VERSION,
                "retrieval_query_sha256": RETRIEVAL_QUERY_SHA256,
                "corpus_fingerprint": CORPUS_FINGERPRINT,
                "ranked_results": ranked_results,
            }
        )

        bm25_ids = {result["chunk_id"] for result in bm25_record["ranked_results"]}
        embedding_ids = {
            result["chunk_id"] for result in embedding_record["ranked_results"]
        }
        overlap = bm25_ids & embedding_ids
        union = bm25_ids | embedding_ids
        all_fused = reciprocal_rank_fusion(
            bm25_record,
            embedding_record,
            rrf_k=RRF_K,
            top_k=len(union),
        )
        diagnostics.append(
            {
                "q_id": q_id,
                "candidate_union_size": len(union),
                "overlap_count": len(overlap),
                "overlap_percentage": 100.0 * len(overlap) / CANDIDATE_DEPTH,
                "overlap_union_percentage": 100.0 * len(overlap) / len(union),
                "bm25_only_count": len(bm25_ids - embedding_ids),
                "embedding_only_count": len(embedding_ids - bm25_ids),
                "both_count": len(overlap),
                "hybrid_score_min": min(
                    result["hybrid_score"] for result in all_fused
                ),
                "hybrid_score_max": max(
                    result["hybrid_score"] for result in all_fused
                ),
            }
        )

    _write_jsonl_atomic(output_path, output_records)
    return {
        "artifact_sha256": sha256_file(output_path),
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "diagnostics": diagnostics,
        "final_result_count": sum(
            len(record["ranked_results"]) for record in output_records
        ),
        "output_path": str(output_path),
        "query_count": len(output_records),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bm25", type=Path, default=DEFAULT_BM25_PATH)
    parser.add_argument("--embedding", type=Path, default=DEFAULT_EMBEDDING_PATH)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args(argv)
    summary = run(
        bm25_path=args.bm25,
        embedding_path=args.embedding,
        query_path=args.queries,
        output_path=args.output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
