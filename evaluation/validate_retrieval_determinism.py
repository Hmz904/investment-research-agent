"""Recompute the gold-blind retrieval determinism sentinel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.verify_frozen_environment import verify_environment
from src.tools.retrieval_tool import RetrievalTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENTINEL_PATH = (
    PROJECT_ROOT
    / "evaluation"
    / "retrieval"
    / "retrieval_determinism_sentinel_v0.1.json"
)


class RetrievalSentinelError(RuntimeError):
    """The sentinel inputs or recomputed ranking violate the frozen contract."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_sentinel(
    *, data_root: Path, model_root: Path, sentinel_path: Path = SENTINEL_PATH
) -> dict[str, Any]:
    sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    rows = sentinel.get("queries")
    if not isinstance(rows, list) or len(rows) != 10:
        raise RetrievalSentinelError("sentinel must contain exactly ten queries")
    query_text = [str(row["query"]) for row in rows]
    if len(set(query_text)) != 10:
        raise RetrievalSentinelError("sentinel queries must be unique")
    if any(len(row.get("ordered_chunk_ids", [])) != 50 for row in rows):
        raise RetrievalSentinelError("each sentinel query must contain 50 chunk IDs")

    query_hash = _sha256(
        (json.dumps(query_text, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )
    if query_hash != sentinel["query_set_sha256"]:
        raise RetrievalSentinelError("query-set SHA-256 mismatch")
    frozen_ranking_hash = _sha256(_canonical_bytes(rows))
    if frozen_ranking_hash != sentinel["ranking_sha256"]:
        raise RetrievalSentinelError("stored ranking SHA-256 mismatch")

    environment = verify_environment()
    if environment["lock_file_sha256"] != sentinel["environment_lock_sha256"]:
        raise RetrievalSentinelError("environment lock identity mismatch")

    tool = RetrievalTool.from_frozen_stack(
        data_root=data_root.resolve(), model_root=model_root.resolve()
    )
    recomputed = []
    for position, query in enumerate(query_text, start=1):
        response = tool.search(query, top_k=50)
        recomputed.append(
            {
                "ordered_chunk_ids": [result.chunk_id for result in response.results],
                "query": query,
            }
        )
        print(f"sentinel query {position}/10 complete", flush=True)
    actual_hash = _sha256(_canonical_bytes(recomputed))
    if actual_hash != frozen_ranking_hash:
        raise RetrievalSentinelError(
            "retrieval ranking drift: "
            f"expected={frozen_ranking_hash} actual={actual_hash}"
        )
    return {
        "query_count": 10,
        "ranking_sha256": actual_hash,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--sentinel", type=Path, default=SENTINEL_PATH)
    args = parser.parse_args()
    print(
        json.dumps(
            validate_sentinel(
                data_root=args.data_root,
                model_root=args.model_root,
                sentinel_path=args.sentinel,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
