"""Run the frozen-query embedding_v0.1 baseline without relevance judgments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.embedding_retrieval import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    DenseRetriever,
    stable_json_line,
)
from src.retrieval import load_ingested_corpus


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data"
DEFAULT_QUERY_PATH = ROOT / "benchmark" / "retrieval_queries_v0.1.csv"
DEFAULT_OUTPUT_PATH = ROOT / "evaluation" / "results" / "embedding_v0.1.jsonl"
DEFAULT_INDEX_CACHE_DIR = ROOT / "data" / "embedding_cache" / "embedding_v0.1"
DEFAULT_MODEL_CACHE_DIR = ROOT / "data" / "model_cache" / "huggingface"

INGESTION_TAG = "ingestion_v0.1.1"
INGESTION_SCHEMA_VERSION = "0.1.1"
CORPUS_FINGERPRINT = "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
EXPECTED_CHUNK_COUNT = 1662
RETRIEVAL_QUERY_VERSION = "retrieval_queries_v0.1.1"
RETRIEVAL_QUERY_SHA256 = "4de3208bf457e0670d691e95284c5675006c825be85a2dca159e6f5268a61c1c"
RETRIEVAL_METHOD = "embedding_v0.1"
EXPECTED_QUERY_COUNT = 16
FROZEN_TOP_K = 50


def _artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_queries(path: Path) -> list[dict[str, str]]:
    actual_hash = _artifact_sha256(path)
    if actual_hash != RETRIEVAL_QUERY_SHA256:
        raise ValueError(
            "frozen retrieval query hash mismatch: "
            f"expected={RETRIEVAL_QUERY_SHA256} actual={actual_hash}"
        )
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["q_id", "query_en"]:
            raise ValueError(
                "frozen retrieval query file must contain exactly q_id,query_en; "
                f"got {reader.fieldnames}"
            )
        rows = [dict(row) for row in reader]
    identifiers = [row["q_id"] for row in rows]
    if len(rows) != EXPECTED_QUERY_COUNT:
        raise ValueError(
            f"expected {EXPECTED_QUERY_COUNT} frozen queries; got {len(rows)}"
        )
    if any(not identifier for identifier in identifiers):
        raise ValueError("every retrieval query requires q_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("retrieval query q_id values must be unique")
    return rows


def _score_distribution(scores: Sequence[float]) -> dict[str, float | int]:
    values = np.asarray(scores, dtype=np.float64)
    if not values.size:
        return {"count": 0, "min": 0.0, "median": 0.0, "max": 0.0}
    return {
        "count": int(values.size),
        "min": float(values.min()),
        "median": float(np.percentile(values, 50, method="linear")),
        "max": float(values.max()),
    }


def run(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    query_path: Path = DEFAULT_QUERY_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    index_cache_dir: Path = DEFAULT_INDEX_CACHE_DIR,
    model_cache_dir: Path = DEFAULT_MODEL_CACHE_DIR,
    top_k: int = FROZEN_TOP_K,
    local_files_only: bool = False,
) -> dict[str, Any]:
    if top_k != FROZEN_TOP_K:
        raise ValueError(f"embedding_v0.1 output top_k must equal {FROZEN_TOP_K}")
    corpus = load_ingested_corpus(
        data_dir,
        expected_corpus_fingerprint=CORPUS_FINGERPRINT,
        expected_ingestion_schema_version=INGESTION_SCHEMA_VERSION,
        verify_chunk_hashes=True,
    )
    if len(corpus.records) != EXPECTED_CHUNK_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CHUNK_COUNT} canonical chunks; "
            f"got {len(corpus.records)}"
        )
    queries = _load_queries(query_path)
    retriever = DenseRetriever(
        cache_dir=index_cache_dir,
        model_cache_dir=model_cache_dir,
        local_files_only=local_files_only,
    )
    retriever.build_index(
        corpus.records,
        corpus_fingerprint=corpus.corpus_fingerprint,
    )

    index_metadata = retriever.index_metadata
    embedding_config = {
        **retriever.config,
        "top_k": top_k,
        "indexed_chunk_count": retriever.indexed_chunk_count,
        "ordered_chunk_id_fingerprint": index_metadata[
            "ordered_chunk_id_fingerprint"
        ],
        "indexed_text_fingerprint": index_metadata["indexed_text_fingerprint"],
        "embedding_matrix_sha256": index_metadata["embedding_matrix_sha256"],
        "index_fingerprint": index_metadata["index_fingerprint"],
    }
    records: list[dict[str, Any]] = []
    empty_result_queries = 0
    all_scores: list[float] = []
    for query in queries:
        results = retriever.search(query["query_en"], top_k=top_k)
        if not results:
            empty_result_queries += 1
        all_scores.extend(result.score for result in results)
        records.append(
            {
                "q_id": query["q_id"],
                "query_en": query["query_en"],
                "retrieval_method": RETRIEVAL_METHOD,
                "model_id": DEFAULT_MODEL_ID,
                "model_revision": DEFAULT_MODEL_REVISION,
                "embedding_config": embedding_config,
                "ingestion_tag": INGESTION_TAG,
                "corpus_fingerprint": corpus.corpus_fingerprint,
                "retrieval_query_version": RETRIEVAL_QUERY_VERSION,
                "retrieval_query_sha256": RETRIEVAL_QUERY_SHA256,
                "ranked_results": [result.to_dict() for result in results],
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(stable_json_line(record))
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise

    return {
        **retriever.statistics,
        "model_id": DEFAULT_MODEL_ID,
        "model_revision": DEFAULT_MODEL_REVISION,
        "query_count": len(queries),
        "empty_result_queries": empty_result_queries,
        "score_distribution": _score_distribution(all_scores),
        "corpus_fingerprint": corpus.corpus_fingerprint,
        "retrieval_query_version": RETRIEVAL_QUERY_VERSION,
        "retrieval_query_sha256": RETRIEVAL_QUERY_SHA256,
        "artifact_sha256": _artifact_sha256(output_path),
        "output_path": str(output_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--index-cache-dir", type=Path, default=DEFAULT_INDEX_CACHE_DIR)
    parser.add_argument("--model-cache-dir", type=Path, default=DEFAULT_MODEL_CACHE_DIR)
    parser.add_argument("--top-k", type=int, default=FROZEN_TOP_K)
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="require the pinned model snapshot to be present in model-cache-dir",
    )
    args = parser.parse_args(argv)
    summary = run(
        data_dir=args.data_dir,
        query_path=args.queries,
        output_path=args.output,
        index_cache_dir=args.index_cache_dir,
        model_cache_dir=args.model_cache_dir,
        top_k=args.top_k,
        local_files_only=args.local_files_only,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
