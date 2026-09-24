"""Run the frozen-query BM25 baseline without loading relevance judgments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from src.retrieval import BM25Retriever, load_ingested_corpus


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data"
DEFAULT_QUERY_PATH = ROOT / "benchmark" / "retrieval" / "retrieval_queries_v0.1.csv"
DEFAULT_OUTPUT_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1.jsonl"

INGESTION_TAG = "ingestion_v0.1.1"
INGESTION_SCHEMA_VERSION = "0.1.1"
CORPUS_FINGERPRINT = "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
RETRIEVAL_QUERY_VERSION = "retrieval_queries_v0.1"
RETRIEVAL_METHOD = "bm25"


def _load_queries(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["q_id", "query_en"]:
            raise ValueError(
                "frozen retrieval query file must contain exactly q_id,query_en; "
                f"got {reader.fieldnames}"
            )
        rows = [dict(row) for row in reader]
    identifiers = [row["q_id"] for row in rows]
    if any(not identifier for identifier in identifiers):
        raise ValueError("every retrieval query requires q_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("retrieval query q_id values must be unique")
    return rows


def _artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    query_path: Path = DEFAULT_QUERY_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    top_k: int = 50,
) -> dict[str, Any]:
    if top_k < 50:
        raise ValueError("baseline output top_k must be at least 50")
    corpus = load_ingested_corpus(
        data_dir,
        expected_corpus_fingerprint=CORPUS_FINGERPRINT,
        expected_ingestion_schema_version=INGESTION_SCHEMA_VERSION,
        verify_chunk_hashes=True,
    )
    retriever = BM25Retriever()
    retriever.build_index(corpus.records)
    queries = _load_queries(query_path)

    retrieval_config = {
        **retriever.config,
        "top_k": top_k,
        "indexed_chunk_count": retriever.indexed_chunk_count,
        "index_fingerprint": retriever.index_fingerprint,
    }
    records: list[dict[str, Any]] = []
    empty_result_queries = 0
    for query in queries:
        results = retriever.search(query["query_en"], top_k=top_k)
        if not results:
            empty_result_queries += 1
        records.append(
            {
                "q_id": query["q_id"],
                "query_en": query["query_en"],
                "retrieval_method": RETRIEVAL_METHOD,
                "retrieval_config": retrieval_config,
                "ingestion_tag": INGESTION_TAG,
                "corpus_fingerprint": corpus.corpus_fingerprint,
                "retrieval_query_version": RETRIEVAL_QUERY_VERSION,
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
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise

    return {
        **retriever.statistics,
        "query_count": len(queries),
        "empty_result_queries": empty_result_queries,
        "corpus_fingerprint": corpus.corpus_fingerprint,
        "artifact_sha256": _artifact_sha256(output_path),
        "output_path": str(output_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--top-k", type=int, default=50)
    args = parser.parse_args(argv)
    summary = run(
        data_dir=args.data_dir,
        query_path=args.queries,
        output_path=args.output,
        top_k=args.top_k,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
