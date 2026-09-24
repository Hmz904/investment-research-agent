"""Score the frozen BM25 output against the finalized provenance gold map.

This module is evaluation-only.  It reads the already-ranked BM25 JSONL and
never imports or invokes production retrieval code.

Scoring interpretation
----------------------
Evidence follows the final gold Boolean structure literally: parts in an item
are AND requirements, while candidate chunks in one part are OR alternatives.
The finalized parts are the scoring units; superseded pre-merge atoms are not
reconstructed.  Item coverage is the fraction of final parts hit and strict
item recovery requires every final part.

Numeric scoring follows both the final provenance artifact and the frozen
benchmark protocol.  A direct fact is retrieved when any approved candidate
chunk is retrieved.  A derived fact is retrieved only when *all* of its
``input_fact_ids`` are retrieved, recursively; its ``candidate_chunk_ids``
field is a provenance union and is never treated as an OR shortcut.  Only
``role=answer`` facts participate directly in numeric question scoring.
Verified answer variants in an ``answer_group`` are OR alternatives, and the
answer groups in a question are AND requirements.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR = ROOT / "benchmark" / "provenance" / "gold"
QUERY_PATH = ROOT / "benchmark" / "retrieval_queries_v0.1.csv"
RESULT_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1.jsonl"
SCORES_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1_scores.json"
PER_QUESTION_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1_per_question.csv"
MISSES_PATH = ROOT / "evaluation" / "results" / "bm25_v0.1_misses.csv"

K_VALUES = (1, 3, 5, 10, 20, 50)
MISS_K_VALUES = (10, 50)
GOLD_MAP_VERSION = "gold_map_v0.1"
GOLD_MAP_FINGERPRINT = (
    "dfc5246bc625085b9412eb0918444751f944930905fbbd4b33cb97adda50ed57"
)
BENCHMARK_VERSION = "bench_v0.1.1"
BM25_VERSION = "bm25_v0.1"
RETRIEVAL_QUERY_VERSION = "retrieval_queries_v0.1"
BM25_RESULT_SHA256 = (
    "7e276b409b9bebafa3b31acc105d253f90595bf652e2936446995bd5ae6611e1"
)
EMBEDDING_RESULT_SHA256 = (
    "d997bb8ac72ba2e003eea440b0e805e3dd9722b053874162bee7d6754bc2bfa3"
)
RERANKER_RESULT_SHA256 = (
    "a1df7aec78ae883c0a5e5e66b217c68c9c9c0d80a705e3f8eb59317b01d9125b"
)
RETRIEVAL_QUERY_SHA256 = (
    "4de3208bf457e0670d691e95284c5675006c825be85a2dca159e6f5268a61c1c"
)
CORPUS_FINGERPRINT = (
    "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
)
EMBEDDING_MODEL_ID = "BAAI/bge-base-en-v1.5"
EMBEDDING_MODEL_REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
RERANKER_MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
IMPORTANCE_WEIGHTS = {"core": 3.0, "supporting": 1.5, "optional": 0.5}

PER_QUESTION_FIELDS = (
    "domain", "q_id", "k", "total_parts", "hit_parts", "mean_part_recall",
    "total_items", "mean_item_coverage", "all_parts_items", "all_parts_rate",
    "weighted_item_coverage", "weighted_evidence_score", "core_item_coverage",
    "core_evidence_recall", "zero_hit_items", "answer_facts",
    "strict_answer_facts", "answer_fact_coverage",
    "mean_answer_fact_input_coverage", "answer_groups", "hit_answer_groups",
    "numeric_group_coverage", "numeric_question_complete",
    "strict_multi_input_fact_count", "strict_multi_input_hit_count",
    "strict_complete_input_retrieval_rate",
)
MISS_FIELDS = (
    "domain", "q_id", "k", "item_or_fact_id", "answer_group", "status",
    "total_required_parts", "hit_parts", "missing_part_ids",
    "approved_gold_candidate_chunk_ids", "missing_gold_candidate_chunk_ids",
    "retrieved_top_k_chunk_ids", "relevant_document_wrong_chunk",
    "first_relevant_rank_below_k", "failure_types",
)
COMPARISON_FIELDS = (
    "scope", "domain", "q_id", "k", "metric", "bm25_v0.1",
    "embedding_v0.1", "absolute_difference",
)
THREE_WAY_COMPARISON_FIELDS = (
    "scope", "domain", "q_id", "k", "metric", "bm25_v0.1",
    "embedding_v0.1", "hybrid_v0.1", "hybrid_minus_bm25",
    "hybrid_minus_embedding",
)
FOUR_WAY_COMPARISON_FIELDS = (
    "scope", "domain", "q_id", "k", "metric", "bm25_v0.1",
    "embedding_v0.1", "hybrid_v0.1", "reranker_v0.1",
    "hybrid_minus_bm25", "hybrid_minus_embedding", "reranker_minus_bm25",
    "reranker_minus_embedding", "reranker_minus_hybrid",
)

EVIDENCE_COMPARISON_METRICS = (
    ("part_recall", "mean_part_recall"),
    ("item_coverage", "mean_item_coverage"),
    ("all_parts_rate", "all_parts_rate"),
    ("benchmark_weighted_strict_score", "weighted_evidence_score"),
    ("weighted_partial_coverage", "weighted_item_coverage"),
    ("core_recall", "core_evidence_recall"),
)
NUMERIC_COMPARISON_METRICS = (
    ("strict_fact_coverage", "answer_fact_coverage"),
    ("group_coverage", "numeric_group_coverage"),
    ("strict_multi_input_rate", "strict_complete_input_retrieval_rate"),
    ("complete_question_rate", "numeric_question_complete_rate"),
    ("mean_input_coverage", "mean_answer_fact_input_coverage"),
)


class EvaluationError(ValueError):
    """Raised when a frozen evaluation input violates its declared schema."""


@dataclass(frozen=True)
class FrozenSystem:
    """Metadata adapter for one immutable ranked-result schema."""

    version: str
    retrieval_method: str
    query_version: str
    config_field: str | None
    result_sha256: str
    artifact_type: str
    result_binding_key: str
    version_binding_key: str
    required_metadata: tuple[tuple[str, Any], ...] = ()
    config_metadata_fields: tuple[str, ...] = ()
    result_depth: int | None = None
    ingestion_tag: str | None = None


BM25_SYSTEM = FrozenSystem(
    version=BM25_VERSION,
    retrieval_method="bm25",
    query_version=RETRIEVAL_QUERY_VERSION,
    config_field="retrieval_config",
    result_sha256=BM25_RESULT_SHA256,
    artifact_type="frozen_bm25_retrieval_evaluation",
    result_binding_key="bm25_result_sha256",
    version_binding_key="bm25_version",
)
EMBEDDING_SYSTEM = FrozenSystem(
    version="embedding_v0.1",
    retrieval_method="embedding_v0.1",
    query_version="retrieval_queries_v0.1.1",
    config_field="embedding_config",
    result_sha256=EMBEDDING_RESULT_SHA256,
    artifact_type="frozen_embedding_retrieval_evaluation",
    result_binding_key="embedding_result_sha256",
    version_binding_key="embedding_version",
    required_metadata=(
        ("retrieval_query_sha256", RETRIEVAL_QUERY_SHA256),
        ("model_id", EMBEDDING_MODEL_ID),
        ("model_revision", EMBEDDING_MODEL_REVISION),
    ),
)
HYBRID_SYSTEM = FrozenSystem(
    version="hybrid_v0.1",
    retrieval_method="hybrid_v0.1",
    query_version="retrieval_queries_v0.1.1",
    config_field=None,
    result_sha256=(
        "17f2f07fd24163b443dd3909aaa81fd188a8dbef77786532d7eb432094769846"
    ),
    artifact_type="frozen_hybrid_retrieval_evaluation",
    result_binding_key="hybrid_result_sha256",
    version_binding_key="hybrid_version",
    required_metadata=(
        ("retrieval_query_sha256", RETRIEVAL_QUERY_SHA256),
        ("bm25_input_artifact_sha256", BM25_RESULT_SHA256),
        ("bm25_version", BM25_VERSION),
        ("embedding_input_artifact_sha256", EMBEDDING_RESULT_SHA256),
        ("embedding_version", "embedding_v0.1"),
        ("embedding_model", EMBEDDING_MODEL_ID),
        ("embedding_model_revision", EMBEDDING_MODEL_REVISION),
        ("fusion_method", "reciprocal_rank_fusion"),
        ("rrf_k", 60),
        ("component_weights", {"bm25": 1.0, "embedding": 1.0}),
        ("candidate_depth", {"bm25": 50, "embedding": 50}),
    ),
    config_metadata_fields=(
        "fusion_method", "rrf_k", "component_weights", "candidate_depth",
    ),
    result_depth=50,
    ingestion_tag="ingestion_v0.1.1",
)
RERANKER_SYSTEM = FrozenSystem(
    version="reranker_v0.1",
    retrieval_method="reranker_v0.1",
    query_version="retrieval_queries_v0.1.1",
    config_field=None,
    result_sha256=RERANKER_RESULT_SHA256,
    artifact_type="frozen_reranker_retrieval_evaluation",
    result_binding_key="reranker_result_sha256",
    version_binding_key="reranker_version",
    required_metadata=(
        ("retrieval_query_sha256", RETRIEVAL_QUERY_SHA256),
        ("bm25_input_artifact_sha256", BM25_RESULT_SHA256),
        ("embedding_input_artifact_sha256", EMBEDDING_RESULT_SHA256),
        (
            "hybrid_input_artifact_sha256",
            "17f2f07fd24163b443dd3909aaa81fd188a8dbef77786532d7eb432094769846",
        ),
        ("model_id", RERANKER_MODEL_ID),
        ("model_revision", RERANKER_MODEL_REVISION),
        ("max_length", 1024),
        (
            "candidate_pool",
            {
                "version": "bm25_v0.1_top50_union_embedding_v0.1_top50",
                "definition": (
                    "frozen bm25_v0.1 top50 UNION frozen embedding_v0.1 top50"
                ),
                "deduplication_key": "chunk_id",
                "bm25_depth": 50,
                "embedding_depth": 50,
            },
        ),
    ),
    config_metadata_fields=(
        "candidate_pool", "model_id", "model_revision", "model_file_sha256",
        "max_length", "runtime_config",
    ),
    result_depth=50,
    ingestion_tag="ingestion_v0.1.1",
)
FROZEN_SYSTEMS = (BM25_SYSTEM, EMBEDDING_SYSTEM, HYBRID_SYSTEM, RERANKER_SYSTEM)


@dataclass(frozen=True)
class Requirement:
    """One AND-required atomic provenance fact with OR candidate chunks."""

    requirement_id: str
    candidate_chunk_ids: tuple[str, ...]
    accessions: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvaluationError(f"expected a JSON object in {path}")
    return payload


def load_queries(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["q_id", "query_en"]:
            raise EvaluationError("retrieval query artifact has an unexpected schema")
        queries: dict[str, str] = {}
        for row_number, row in enumerate(reader, start=2):
            q_id = row.get("q_id", "")
            query = row.get("query_en", "")
            if not q_id or not query:
                raise EvaluationError(f"missing q_id/query_en on query row {row_number}")
            if q_id in queries:
                raise EvaluationError(f"duplicate retrieval query q_id: {q_id}")
            queries[q_id] = query
    if not queries:
        raise EvaluationError("retrieval query artifact is empty")
    return queries


def load_ranked_results(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise EvaluationError(f"blank JSONL record at line {line_number}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvaluationError(
                    f"malformed ranked-result JSONL at line {line_number}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise EvaluationError(f"ranked-result record {line_number} is not an object")
            if "q_id" not in record:
                raise EvaluationError(f"ranked-result record {line_number} has missing q_id")
            records.append(record)
    if not records:
        raise EvaluationError("BM25 result artifact is empty")
    return records


def _retrieval_config(record: dict[str, Any], system: FrozenSystem) -> dict[str, Any]:
    """Return one system's frozen configuration without changing score semantics."""
    if system.config_field is not None:
        config = record.get(system.config_field)
        if not isinstance(config, dict):
            raise EvaluationError(f"missing retrieval config for {record.get('q_id')}")
        return config
    config = {field: record.get(field) for field in system.config_metadata_fields}
    if any(value is None for value in config.values()):
        raise EvaluationError(f"missing retrieval config for {record.get('q_id')}")
    return config


def validate_ranked_results(
    records: Sequence[dict[str, Any]],
    queries: dict[str, str],
    system: FrozenSystem = BM25_SYSTEM,
) -> dict[str, dict[str, Any]]:
    by_q: dict[str, dict[str, Any]] = {}
    configs: set[str] = set()
    corpus_fingerprints: set[str] = set()
    for record in records:
        q_id = record["q_id"]
        if not isinstance(q_id, str) or not q_id:
            raise EvaluationError("ranked-result q_id must be a non-empty string")
        if q_id in by_q:
            raise EvaluationError(f"duplicate ranked-result q_id: {q_id}")
        if q_id not in queries:
            raise EvaluationError(f"unknown ranked-result q_id: {q_id}")
        if record.get("query_en") != queries[q_id]:
            raise EvaluationError(f"frozen query text mismatch for {q_id}")
        if record.get("retrieval_query_version") != system.query_version:
            raise EvaluationError(f"retrieval query version mismatch for {q_id}")
        if record.get("retrieval_method") != system.retrieval_method:
            raise EvaluationError(f"retrieval method mismatch for {q_id}")
        config = _retrieval_config(record, system)
        configs.add(json.dumps(config, sort_keys=True))
        for field, expected in system.required_metadata:
            if record.get(field) != expected:
                raise EvaluationError(f"{field} mismatch for {q_id}")
        fingerprint = record.get("corpus_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise EvaluationError(f"missing corpus fingerprint for {q_id}")
        corpus_fingerprints.add(fingerprint)
        ranked = record.get("ranked_results")
        if not isinstance(ranked, list) or len(ranked) < max(K_VALUES):
            raise EvaluationError(f"{q_id} has fewer than {max(K_VALUES)} saved results")
        if system.result_depth is not None and len(ranked) != system.result_depth:
            raise EvaluationError(f"{q_id} has unexpected frozen result depth")
        expected_ranks = list(range(1, len(ranked) + 1))
        actual_ranks = [result.get("rank") for result in ranked]
        if actual_ranks != expected_ranks:
            raise EvaluationError(f"non-contiguous result ranks for {q_id}")
        chunk_ids = [result.get("chunk_id") for result in ranked]
        if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids):
            raise EvaluationError(f"missing ranked chunk_id for {q_id}")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise EvaluationError(f"duplicate ranked chunk_id for {q_id}")
        if any(not result.get("accession") for result in ranked):
            raise EvaluationError(f"missing ranked accession for {q_id}")
        by_q[q_id] = record
    if set(by_q) != set(queries):
        missing = sorted(set(queries) - set(by_q))
        raise EvaluationError(f"ranked results are missing q_ids: {missing}")
    if len(configs) != 1:
        raise EvaluationError("retrieval config differs across questions")
    if len(corpus_fingerprints) != 1:
        raise EvaluationError("corpus fingerprint differs across ranked-result records")
    config = _retrieval_config(records[0], system)
    if system.config_field is not None and config.get("top_k", 0) < max(K_VALUES):
        raise EvaluationError("saved top_k does not support requested K values")
    return by_q


def _ordered_union(values: Iterable[Iterable[str]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in values:
        for value in group:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
    return ordered


def validate_gold_manifest(gold_dir: Path, manifest: dict[str, Any]) -> None:
    """Verify the declared fingerprint and every artifact bound by it."""
    if manifest.get("fingerprint_algorithm") != "sha256-canonical-json":
        raise EvaluationError("unexpected gold fingerprint algorithm")
    fingerprint_payload = dict(manifest)
    declared_fingerprint = fingerprint_payload.pop("gold_map_fingerprint", None)
    fingerprint_payload.pop("timestamps", None)
    actual_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if declared_fingerprint != actual_fingerprint:
        raise EvaluationError("gold manifest fingerprint validation failed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise EvaluationError("gold manifest has no artifact bindings")
    for name, metadata in artifacts.items():
        if not isinstance(name, str) or not isinstance(metadata, dict):
            raise EvaluationError("malformed gold artifact binding")
        path = gold_dir / name
        if not path.is_file():
            raise EvaluationError(f"gold artifact is missing: {name}")
        if path.stat().st_size != metadata.get("bytes"):
            raise EvaluationError(f"gold artifact byte count mismatch: {name}")
        if sha256_file(path) != metadata.get("sha256"):
            raise EvaluationError(f"gold artifact SHA-256 mismatch: {name}")


def validate_gold(
    evidence: dict[str, Any],
    numeric: dict[str, Any],
    manifest: dict[str, Any],
    version_binding: dict[str, Any],
    result_q_ids: set[str],
) -> None:
    if manifest.get("gold_map_fingerprint") != GOLD_MAP_FINGERPRINT:
        raise EvaluationError("gold map fingerprint does not match gold_map_v0.1")
    benchmark = manifest.get("benchmark_binding", {})
    if benchmark.get("benchmark_version") != BENCHMARK_VERSION:
        raise EvaluationError("gold benchmark version mismatch")
    if version_binding.get("benchmark_version") != BENCHMARK_VERSION:
        raise EvaluationError("gold version binding mismatch")
    if evidence.get("boolean_semantics") != (
        "AND across parts; OR among candidate_sources within each part"
    ):
        raise EvaluationError("unexpected evidence Boolean semantics")
    if numeric.get("boolean_semantics") != (
        "OR among candidate_sources for a direct fact; derived facts require all input_fact_ids"
    ):
        raise EvaluationError("unexpected numeric Boolean semantics")

    items = evidence.get("items")
    if not isinstance(items, list) or evidence.get("verified_item_count") != len(items):
        raise EvaluationError("evidence item count mismatch")
    evidence_ids: set[tuple[str, str]] = set()
    evidence_q_ids: set[str] = set()
    for item in items:
        q_id, item_id = item.get("q_id"), item.get("item_id")
        if not q_id or not item_id:
            raise EvaluationError("evidence item has missing q_id/item_id")
        key = (q_id, item_id)
        if key in evidence_ids:
            raise EvaluationError(f"duplicate evidence item: {key}")
        evidence_ids.add(key)
        evidence_q_ids.add(q_id)
        if q_id not in result_q_ids:
            raise EvaluationError(f"evidence q_id has no BM25 result: {q_id}")
        if item.get("parts_operator") != "AND":
            raise EvaluationError(f"evidence item is not AND-structured: {key}")
        if item.get("importance") not in IMPORTANCE_WEIGHTS:
            raise EvaluationError(f"unknown importance for evidence item {key}")
        parts = item.get("parts")
        if not isinstance(parts, list) or not parts:
            raise EvaluationError(f"evidence item has no parts: {key}")
        if item.get("part_count") != len(parts):
            raise EvaluationError(f"evidence part count mismatch: {key}")
        part_ids: set[str] = set()
        for part in parts:
            part_id = part.get("part_id")
            if not isinstance(part_id, str) or not part_id or part_id in part_ids:
                raise EvaluationError(f"invalid evidence part id in {key}")
            part_ids.add(part_id)
            if part.get("candidates_operator") != "OR":
                raise EvaluationError(
                    f"evidence part is not OR-structured: {q_id}/{item_id}/{part_id}"
                )
            sources = part.get("candidate_sources")
            candidates = part.get("candidate_chunk_ids")
            if not isinstance(sources, list) or not isinstance(candidates, list) or not candidates:
                raise EvaluationError(f"evidence part has no candidates: {q_id}/{item_id}/{part_id}")
            if candidates != [source.get("chunk_id") for source in sources]:
                raise EvaluationError(
                    f"evidence candidates disagree with sources: {q_id}/{item_id}/{part_id}"
                )

    facts = numeric.get("facts")
    if not isinstance(facts, list) or numeric.get("fact_count") != len(facts):
        raise EvaluationError("numeric fact count mismatch")
    facts_by_id: dict[str, dict[str, Any]] = {}
    for fact in facts:
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str) or not fact_id or fact_id in facts_by_id:
            raise EvaluationError(f"invalid or duplicate numeric fact_id: {fact_id}")
        facts_by_id[fact_id] = fact
        sources = fact.get("candidate_sources")
        candidates = fact.get("candidate_chunk_ids")
        if not isinstance(sources, list) or not isinstance(candidates, list) or not candidates:
            raise EvaluationError(f"numeric fact has no candidates: {fact_id}")
        if candidates != [source.get("chunk_id") for source in sources]:
            raise EvaluationError(f"numeric candidates disagree with sources: {fact_id}")
        inputs = fact.get("input_fact_ids")
        if not isinstance(inputs, list) or any(not isinstance(value, str) for value in inputs):
            raise EvaluationError(f"numeric fact inputs are malformed: {fact_id}")

    numeric_q_ids: set[str] = set()
    for fact in facts:
        fact_id = fact["fact_id"]
        status = fact.get("status")
        inputs = fact["input_fact_ids"]
        if status in {"direct_unique", "direct_or"}:
            if inputs or fact.get("is_derived"):
                raise EvaluationError(f"direct numeric fact has derived fields: {fact_id}")
            if status == "direct_unique" and len(fact["candidate_chunk_ids"]) != 1:
                raise EvaluationError(f"direct_unique fact is not unique: {fact_id}")
            if status == "direct_or" and len(fact["candidate_chunk_ids"]) < 2:
                raise EvaluationError(f"direct_or fact lacks alternatives: {fact_id}")
        elif status == "derived":
            if not inputs or not fact.get("is_derived"):
                raise EvaluationError(f"derived numeric fact lacks inputs: {fact_id}")
            missing_inputs = [input_id for input_id in inputs if input_id not in facts_by_id]
            if missing_inputs:
                raise EvaluationError(f"derived fact {fact_id} has unknown inputs: {missing_inputs}")
            expected_union = _ordered_union(
                facts_by_id[input_id]["candidate_chunk_ids"] for input_id in inputs
            )
            if fact["candidate_chunk_ids"] != expected_union:
                raise EvaluationError(
                    f"derived provenance union does not match required inputs: {fact_id}"
                )
        else:
            raise EvaluationError(f"unknown numeric fact status: {status}")
        role = fact.get("role")
        if role == "answer":
            q_id, answer_group = fact.get("q_id"), fact.get("answer_group")
            if not q_id or not answer_group:
                raise EvaluationError(f"answer fact lacks q_id/group: {fact_id}")
            if q_id not in result_q_ids:
                raise EvaluationError(f"numeric q_id has no BM25 result: {q_id}")
            numeric_q_ids.add(q_id)
        elif role != "input":
            raise EvaluationError(f"unknown numeric fact role: {role}")

    def visit(fact_id: str, stack: tuple[str, ...]) -> None:
        if fact_id in stack:
            raise EvaluationError(f"numeric dependency cycle: {' -> '.join(stack + (fact_id,))}")
        fact = facts_by_id[fact_id]
        for input_id in fact["input_fact_ids"]:
            visit(input_id, stack + (fact_id,))

    for fact_id in facts_by_id:
        visit(fact_id, ())
    if evidence_q_ids & numeric_q_ids:
        raise EvaluationError("a q_id appears in both evidence and numeric scoring sets")
    if evidence_q_ids | numeric_q_ids != result_q_ids:
        raise EvaluationError("gold scoring q_ids do not exactly match BM25 q_ids")


class NumericProvenance:
    """Resolve derived facts to recursive AND requirements without shortcuts."""

    def __init__(self, facts: Sequence[dict[str, Any]]) -> None:
        self.facts_by_id = {fact["fact_id"]: fact for fact in facts}
        self._cache: dict[str, tuple[Requirement, ...]] = {}

    def requirements(self, fact_id: str) -> tuple[Requirement, ...]:
        return self._requirements(fact_id, ())

    def _requirements(
        self, fact_id: str, stack: tuple[str, ...]
    ) -> tuple[Requirement, ...]:
        if fact_id in self._cache:
            return self._cache[fact_id]
        if fact_id in stack:
            raise EvaluationError(f"numeric dependency cycle at {fact_id}")
        fact = self.facts_by_id[fact_id]
        if fact["status"] in {"direct_unique", "direct_or"}:
            result = (
                Requirement(
                    requirement_id=fact_id,
                    candidate_chunk_ids=tuple(fact["candidate_chunk_ids"]),
                    accessions=tuple(
                        dict.fromkeys(source["accession"] for source in fact["candidate_sources"])
                    ),
                ),
            )
        else:
            expanded: list[Requirement] = []
            seen: set[str] = set()
            for input_id in fact["input_fact_ids"]:
                for requirement in self._requirements(input_id, stack + (fact_id,)):
                    if requirement.requirement_id not in seen:
                        seen.add(requirement.requirement_id)
                        expanded.append(requirement)
            result = tuple(expanded)
        self._cache[fact_id] = result
        return result


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise EvaluationError("cannot compute a metric with a zero denominator")
    return round(numerator / denominator, 12)


def _rank_index(
    record: dict[str, Any],
) -> tuple[dict[str, int], dict[int, dict[str, Any]]]:
    by_chunk = {result["chunk_id"]: result["rank"] for result in record["ranked_results"]}
    by_rank = {result["rank"]: result for result in record["ranked_results"]}
    return by_chunk, by_rank


def _first_rank(candidates: Sequence[str], rank_by_chunk: dict[str, int]) -> int | None:
    ranks = [rank_by_chunk[candidate] for candidate in candidates if candidate in rank_by_chunk]
    return min(ranks) if ranks else None


def _evidence_item_state(
    item: dict[str, Any], rank_by_chunk: dict[str, int], k: int
) -> dict[str, Any]:
    parts = []
    for part in item["parts"]:
        first_rank = _first_rank(part["candidate_chunk_ids"], rank_by_chunk)
        parts.append({"part": part, "first_rank": first_rank, "hit": first_rank is not None and first_rank <= k})
    hit_count = sum(state["hit"] for state in parts)
    return {
        "parts": parts,
        "hit_count": hit_count,
        "coverage": _ratio(hit_count, len(parts)),
        "all_parts": hit_count == len(parts),
    }


def evidence_metrics(
    items: Sequence[dict[str, Any]],
    results_by_q: dict[str, dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    states = []
    for item in items:
        rank_by_chunk, _ = _rank_index(results_by_q[item["q_id"]])
        states.append((item, _evidence_item_state(item, rank_by_chunk, k)))
    total_parts = sum(len(item["parts"]) for item, _ in states)
    hit_parts = sum(state["hit_count"] for _, state in states)
    total_items = len(states)
    all_parts_items = sum(state["all_parts"] for _, state in states)
    total_weight = sum(IMPORTANCE_WEIGHTS[item["importance"]] for item, _ in states)
    weighted_coverage = sum(
        IMPORTANCE_WEIGHTS[item["importance"]] * state["coverage"]
        for item, state in states
    )
    weighted_strict = sum(
        IMPORTANCE_WEIGHTS[item["importance"]] * state["all_parts"]
        for item, state in states
    )
    core = [(item, state) for item, state in states if item["importance"] == "core"]
    core_coverage = sum(state["coverage"] for _, state in core)
    core_strict = sum(state["all_parts"] for _, state in core)
    first_hit_counts: Counter[str] = Counter()
    reciprocal_rank_sum = 0.0
    for _, state in states:
        for part_state in state["parts"]:
            first_rank = part_state["first_rank"]
            label = str(first_rank) if first_rank is not None else "not_in_top50"
            first_hit_counts[label] += 1
            if first_rank is not None:
                reciprocal_rank_sum += 1.0 / first_rank
    return {
        "total_parts": total_parts,
        "hit_parts": hit_parts,
        "mean_part_recall": _ratio(hit_parts, total_parts),
        "total_items": total_items,
        "mean_item_coverage": _ratio(sum(s["coverage"] for _, s in states), total_items),
        "all_parts_items": all_parts_items,
        "all_parts_rate": _ratio(all_parts_items, total_items),
        "weighted_item_coverage": _ratio(weighted_coverage, total_weight),
        "weighted_evidence_score": _ratio(weighted_strict, total_weight),
        "core_item_coverage": _ratio(core_coverage, len(core)),
        "core_evidence_recall": _ratio(core_strict, len(core)),
        "zero_hit_items": sum(s["hit_count"] == 0 for _, s in states),
        "atomic_part_mrr_at_50": round(reciprocal_rank_sum / total_parts, 12),
        "first_hit_rank_distribution": dict(
            sorted(
                first_hit_counts.items(),
                key=lambda pair: int(pair[0]) if pair[0].isdigit() else 1_000_000_000,
            )
        ),
    }


def _fact_state(
    fact: dict[str, Any],
    provenance: NumericProvenance,
    rank_by_chunk: dict[str, int],
    k: int,
) -> dict[str, Any]:
    requirements = provenance.requirements(fact["fact_id"])
    states = []
    for requirement in requirements:
        first_rank = _first_rank(requirement.candidate_chunk_ids, rank_by_chunk)
        states.append(
            {"requirement": requirement, "first_rank": first_rank, "hit": first_rank is not None and first_rank <= k}
        )
    hit_count = sum(state["hit"] for state in states)
    return {
        "requirements": states,
        "hit_count": hit_count,
        "input_coverage": _ratio(hit_count, len(states)),
        "strict": hit_count == len(states),
    }


def numeric_metrics(
    answer_facts: Sequence[dict[str, Any]],
    provenance: NumericProvenance,
    results_by_q: dict[str, dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    fact_states = {}
    for fact in answer_facts:
        rank_by_chunk, _ = _rank_index(results_by_q[fact["q_id"]])
        fact_states[fact["fact_id"]] = _fact_state(fact, provenance, rank_by_chunk, k)
    groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in answer_facts:
        groups[(fact["q_id"], fact["answer_group"])].append(fact)
    group_hits = {
        key: any(fact_states[fact["fact_id"]]["strict"] for fact in variants)
        for key, variants in groups.items()
    }
    question_groups: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in groups:
        question_groups[key[0]].append(key)
    question_complete = {
        q_id: all(group_hits[key] for key in keys)
        for q_id, keys in question_groups.items()
    }
    multi_input = [
        fact
        for fact in answer_facts
        if fact["status"] == "derived" and len(provenance.requirements(fact["fact_id"])) > 1
    ]
    strict_facts = sum(state["strict"] for state in fact_states.values())
    hit_groups = sum(group_hits.values())
    return {
        "answer_facts": len(answer_facts),
        "strict_answer_facts": strict_facts,
        "answer_fact_coverage": _ratio(strict_facts, len(answer_facts)),
        "mean_answer_fact_input_coverage": _ratio(
            sum(state["input_coverage"] for state in fact_states.values()), len(answer_facts)
        ),
        "answer_groups": len(groups),
        "hit_answer_groups": hit_groups,
        "numeric_group_coverage": _ratio(hit_groups, len(groups)),
        "numeric_questions": len(question_groups),
        "complete_numeric_questions": sum(question_complete.values()),
        "numeric_question_complete_rate": _ratio(sum(question_complete.values()), len(question_groups)),
        "strict_multi_input_fact_count": len(multi_input),
        "strict_multi_input_hit_count": sum(
            fact_states[fact["fact_id"]]["strict"] for fact in multi_input
        ),
        "strict_complete_input_retrieval_rate": (
            _ratio(
                sum(fact_states[fact["fact_id"]]["strict"] for fact in multi_input),
                len(multi_input),
            )
            if multi_input
            else None
        ),
        "zero_hit_answer_facts": sum(state["hit_count"] == 0 for state in fact_states.values()),
    }


def _per_question_rows(
    evidence_items: Sequence[dict[str, Any]],
    answer_facts: Sequence[dict[str, Any]],
    provenance: NumericProvenance,
    results_by_q: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_by_q: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    numeric_by_q: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence_items:
        evidence_by_q[item["q_id"]].append(item)
    for fact in answer_facts:
        numeric_by_q[fact["q_id"]].append(fact)
    rows: list[dict[str, Any]] = []
    for q_id in sorted(results_by_q):
        if q_id in evidence_by_q:
            for k in K_VALUES:
                metrics = evidence_metrics(evidence_by_q[q_id], results_by_q, k)
                row = {field: "" for field in PER_QUESTION_FIELDS}
                row.update({"domain": "evidence", "q_id": q_id, "k": k})
                for field in PER_QUESTION_FIELDS:
                    if field in metrics:
                        row[field] = metrics[field]
                rows.append(row)
        if q_id in numeric_by_q:
            for k in K_VALUES:
                metrics = numeric_metrics(numeric_by_q[q_id], provenance, results_by_q, k)
                row = {field: "" for field in PER_QUESTION_FIELDS}
                row.update({"domain": "numeric", "q_id": q_id, "k": k})
                for field in PER_QUESTION_FIELDS:
                    if field in metrics:
                        row[field] = metrics[field]
                row["numeric_question_complete"] = bool(metrics["complete_numeric_questions"])
                rows.append(row)
    return rows


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _state_requirement(state: dict[str, Any]) -> Requirement:
    if "requirement" in state:
        return state["requirement"]
    part = state["part"]
    return Requirement(
        requirement_id=part["part_id"],
        candidate_chunk_ids=tuple(part["candidate_chunk_ids"]),
        accessions=tuple(dict.fromkeys(source["accession"] for source in part["candidate_sources"])),
    )


def _miss_row(
    domain: str,
    q_id: str,
    k: int,
    item_or_fact_id: str,
    answer_group: str,
    states: Sequence[dict[str, Any]],
    results: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    missing = [state for state in states if not state["hit"]]
    hit_count = len(states) - len(missing)
    missing_requirements = [_state_requirement(state) for state in missing]
    all_requirements = [_state_requirement(state) for state in states]
    top_k = list(results[:k])
    top_50 = list(results[: max(K_VALUES)])
    top_k_chunks = [result["chunk_id"] for result in top_k]
    rank_by_chunk = {result["chunk_id"]: result["rank"] for result in top_50}
    top_k_accessions = {result["accession"] for result in top_k}
    wrong_chunk = any(
        set(requirement.accessions) & top_k_accessions
        for requirement in missing_requirements
    )
    below_ranks = [
        rank_by_chunk[candidate]
        for requirement in missing_requirements
        for candidate in requirement.candidate_chunk_ids
        if candidate in rank_by_chunk and rank_by_chunk[candidate] > k
    ]
    failure_types: list[str] = []
    if hit_count and len(states) > 1:
        failure_types.append("multi_part_partial_hit")
    if below_ranks:
        failure_types.append("relevant_chunk_below_k")
    if wrong_chunk:
        failure_types.append("correct_document_wrong_chunk")
    top_50_accessions = {result["accession"] for result in top_50}
    missing_document_in_top_50 = any(
        not (set(requirement.accessions) & top_50_accessions)
        for requirement in missing_requirements
    )
    if missing_document_in_top_50:
        failure_types.append("no_relevant_document_in_top50")
    if not failure_types:
        failure_types.append("relevant_document_below_k_wrong_chunk")
    return {
        "domain": domain,
        "q_id": q_id,
        "k": k,
        "item_or_fact_id": item_or_fact_id,
        "answer_group": answer_group,
        "status": "partial" if hit_count else "missed",
        "total_required_parts": len(states),
        "hit_parts": hit_count,
        "missing_part_ids": _json_cell([r.requirement_id for r in missing_requirements]),
        "approved_gold_candidate_chunk_ids": _json_cell(
            {r.requirement_id: list(r.candidate_chunk_ids) for r in all_requirements}
        ),
        "missing_gold_candidate_chunk_ids": _json_cell(
            {r.requirement_id: list(r.candidate_chunk_ids) for r in missing_requirements}
        ),
        "retrieved_top_k_chunk_ids": _json_cell(top_k_chunks),
        "relevant_document_wrong_chunk": wrong_chunk,
        "first_relevant_rank_below_k": min(below_ranks) if below_ranks else "",
        "failure_types": ";".join(failure_types),
    }


def build_miss_rows(
    evidence_items: Sequence[dict[str, Any]],
    answer_facts: Sequence[dict[str, Any]],
    provenance: NumericProvenance,
    results_by_q: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for k in MISS_K_VALUES:
        for item in sorted(evidence_items, key=lambda value: (value["q_id"], value["item_id"])):
            record = results_by_q[item["q_id"]]
            rank_by_chunk, _ = _rank_index(record)
            state = _evidence_item_state(item, rank_by_chunk, k)
            if not state["all_parts"]:
                rows.append(
                    _miss_row(
                        "evidence", item["q_id"], k, item["item_id"], "",
                        state["parts"], record["ranked_results"]
                    )
                )
        for fact in sorted(answer_facts, key=lambda value: (value["q_id"], value["fact_id"])):
            record = results_by_q[fact["q_id"]]
            rank_by_chunk, _ = _rank_index(record)
            state = _fact_state(fact, provenance, rank_by_chunk, k)
            if not state["strict"]:
                rows.append(
                    _miss_row(
                        "numeric", fact["q_id"], k, fact["fact_id"], fact["answer_group"],
                        state["requirements"], record["ranked_results"]
                    )
                )
    return rows


def _failure_counts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for k in MISS_K_VALUES:
        output[str(k)] = {}
        for domain in ("evidence", "numeric"):
            selected = [row for row in rows if row["k"] == k and row["domain"] == domain]
            counts: Counter[str] = Counter()
            for row in selected:
                counts.update(value for value in row["failure_types"].split(";") if value)
            output[str(k)][domain] = {
                "diagnostic_rows": len(selected),
                "missed": sum(row["status"] == "missed" for row in selected),
                "partial": sum(row["status"] == "partial" for row in selected),
                "failure_type_counts": dict(sorted(counts.items())),
            }
    return output


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _system_for_result(path: Path) -> FrozenSystem:
    result_sha256 = sha256_file(path)
    for system in FROZEN_SYSTEMS:
        if result_sha256 == system.result_sha256:
            return system
    raise EvaluationError(
        f"ranked-result SHA-256 is not a frozen supported system: {result_sha256}"
    )


def evaluate(
    gold_dir: Path,
    query_path: Path,
    result_path: Path,
    system: FrozenSystem | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load, validate, and score frozen inputs without writing any files."""
    if sha256_file(query_path) != RETRIEVAL_QUERY_SHA256:
        raise EvaluationError("frozen retrieval query artifact SHA-256 mismatch")
    selected_system = system or _system_for_result(result_path)
    if sha256_file(result_path) != selected_system.result_sha256:
        raise EvaluationError(
            f"frozen {selected_system.version} result artifact SHA-256 mismatch"
        )
    evidence_path = gold_dir / "evidence_provenance.json"
    numeric_path = gold_dir / "numeric_fact_provenance.json"
    manifest_path = gold_dir / "gold_manifest.json"
    binding_path = gold_dir / "version_binding.json"
    evidence = _load_json(evidence_path)
    numeric = _load_json(numeric_path)
    manifest = _load_json(manifest_path)
    binding = _load_json(binding_path)
    validate_gold_manifest(gold_dir, manifest)
    queries = load_queries(query_path)
    records = load_ranked_results(result_path)
    results_by_q = validate_ranked_results(records, queries, selected_system)
    validate_gold(evidence, numeric, manifest, binding, set(results_by_q))
    corpus_fingerprint = records[0]["corpus_fingerprint"]
    if corpus_fingerprint != CORPUS_FINGERPRINT:
        raise EvaluationError("ranked-result corpus fingerprint mismatch")
    if corpus_fingerprint != binding.get("corpus_fingerprint"):
        raise EvaluationError("ranked-result corpus fingerprint does not match gold binding")
    ingestion_tag = records[0].get("ingestion_tag", selected_system.ingestion_tag)
    if ingestion_tag != binding.get("ingestion_tag"):
        raise EvaluationError("ranked-result ingestion tag does not match gold binding")
    answer_facts = [fact for fact in numeric["facts"] if fact["role"] == "answer"]
    provenance = NumericProvenance(numeric["facts"])
    evidence_by_k = {
        str(k): evidence_metrics(evidence["items"], results_by_q, k) for k in K_VALUES
    }
    numeric_by_k = {
        str(k): numeric_metrics(answer_facts, provenance, results_by_q, k) for k in K_VALUES
    }
    per_question = _per_question_rows(evidence["items"], answer_facts, provenance, results_by_q)
    misses = build_miss_rows(evidence["items"], answer_facts, provenance, results_by_q)
    result_bindings = {
        selected_system.result_binding_key: selected_system.result_sha256,
        selected_system.version_binding_key: selected_system.version,
    }
    scores = {
        "artifact_type": selected_system.artifact_type,
        "bindings": {
            "benchmark_tag": binding["benchmark_tag"],
            "benchmark_version": binding["benchmark_version"],
            **result_bindings,
            "corpus_fingerprint": corpus_fingerprint,
            "gold_artifact_sha256": {
                name: sha256_file(gold_dir / name)
                for name in (
                    "evidence_provenance.json", "gold_manifest.json", "merge_lineage.json",
                    "numeric_fact_provenance.json", "review_decisions.json",
                    "source_anchors.json", "version_binding.json",
                )
            },
            "gold_map_fingerprint": GOLD_MAP_FINGERPRINT,
            "gold_map_version": GOLD_MAP_VERSION,
            "ingestion_tag": ingestion_tag,
            "retrieval_config": _retrieval_config(records[0], selected_system),
            "retrieval_query_artifact_sha256": RETRIEVAL_QUERY_SHA256,
            "retrieval_query_version": selected_system.query_version,
        },
        "k_values": list(K_VALUES),
        "scoring_interpretation": {
            "evidence": (
                "Final evidence parts are AND requirements; approved candidate chunks "
                "within each part are OR alternatives. Final approved merge lineage is used as-is."
            ),
            "numeric": (
                "Direct-fact candidates are OR alternatives; derived facts recursively require "
                "every input_fact_id. Answer variants within a group are OR and answer groups "
                "within a question are AND. Input-role facts are provenance requirements, not "
                "independently scored answers."
            ),
            "weighted_evidence": {
                "importance_weights": IMPORTANCE_WEIGHTS,
                "weighted_evidence_score": "importance-weighted strict all-parts item recovery",
                "weighted_item_coverage": "importance-weighted partial item coverage",
            },
        },
        "counts": {
            "evidence_items": len(evidence["items"]),
            "evidence_parts": sum(len(item["parts"]) for item in evidence["items"]),
            "numeric_facts_in_gold": len(numeric["facts"]),
            "numeric_answer_facts": len(answer_facts),
            "questions": len(results_by_q),
        },
        "evidence_metrics": evidence_by_k,
        "numeric_metrics": numeric_by_k,
        "miss_diagnostics": _failure_counts(misses),
    }
    return scores, per_question, misses


def _comparison_value(value: Any) -> Any:
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return int(value)
    return value


def _comparison_row(
    scope: str,
    domain: str,
    q_id: str,
    k: int,
    metric: str,
    bm25_value: Any,
    embedding_value: Any,
) -> dict[str, Any]:
    bm25_value = _comparison_value(bm25_value)
    embedding_value = _comparison_value(embedding_value)
    if bm25_value == "" or embedding_value == "":
        difference: float | str = ""
    else:
        difference = round(abs(float(embedding_value) - float(bm25_value)), 12)
    return {
        "scope": scope,
        "domain": domain,
        "q_id": q_id,
        "k": k,
        "metric": metric,
        "bm25_v0.1": bm25_value,
        "embedding_v0.1": embedding_value,
        "absolute_difference": difference,
    }


def build_comparison_rows(
    bm25_scores: dict[str, Any],
    bm25_per_question: Sequence[dict[str, Any]],
    embedding_scores: dict[str, Any],
    embedding_per_question: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare the complete frozen metric panel on its original absolute scale."""
    if bm25_scores.get("k_values") != list(K_VALUES):
        raise EvaluationError("BM25 scores do not contain the frozen K values")
    if embedding_scores.get("k_values") != list(K_VALUES):
        raise EvaluationError("embedding scores do not contain the frozen K values")
    rows: list[dict[str, Any]] = []
    metric_groups = (
        ("evidence", "evidence_metrics", EVIDENCE_COMPARISON_METRICS),
        ("numeric", "numeric_metrics", NUMERIC_COMPARISON_METRICS),
    )
    for domain, score_key, metrics in metric_groups:
        for k in K_VALUES:
            bm25_at_k = bm25_scores[score_key][str(k)]
            embedding_at_k = embedding_scores[score_key][str(k)]
            for metric, field in metrics:
                rows.append(
                    _comparison_row(
                        "aggregate", domain, "", k, metric,
                        bm25_at_k[field], embedding_at_k[field],
                    )
                )

    bm25_by_question = {
        (row["domain"], row["q_id"], int(row["k"])): row
        for row in bm25_per_question
    }
    embedding_by_question = {
        (row["domain"], row["q_id"], int(row["k"])): row
        for row in embedding_per_question
    }
    if set(bm25_by_question) != set(embedding_by_question):
        raise EvaluationError("per-question comparison keys differ between systems")
    per_question_fields = {
        "evidence": EVIDENCE_COMPARISON_METRICS,
        "numeric": tuple(
            (
                metric,
                "numeric_question_complete"
                if field == "numeric_question_complete_rate"
                else field,
            )
            for metric, field in NUMERIC_COMPARISON_METRICS
        ),
    }
    for domain, q_id, k in sorted(bm25_by_question):
        bm25_row = bm25_by_question[(domain, q_id, k)]
        embedding_row = embedding_by_question[(domain, q_id, k)]
        for metric, field in per_question_fields[domain]:
            rows.append(
                _comparison_row(
                    "per_question", domain, q_id, k, metric,
                    bm25_row[field], embedding_row[field],
                )
            )
    return rows


def _three_way_comparison_row(
    scope: str,
    domain: str,
    q_id: str,
    k: int,
    metric: str,
    bm25_value: Any,
    embedding_value: Any,
    hybrid_value: Any,
) -> dict[str, Any]:
    values = tuple(
        _comparison_value(value)
        for value in (bm25_value, embedding_value, hybrid_value)
    )
    bm25_value, embedding_value, hybrid_value = values
    hybrid_minus_bm25: float | str = ""
    hybrid_minus_embedding: float | str = ""
    if hybrid_value != "" and bm25_value != "":
        hybrid_minus_bm25 = round(float(hybrid_value) - float(bm25_value), 12)
    if hybrid_value != "" and embedding_value != "":
        hybrid_minus_embedding = round(float(hybrid_value) - float(embedding_value), 12)
    return {
        "scope": scope,
        "domain": domain,
        "q_id": q_id,
        "k": k,
        "metric": metric,
        "bm25_v0.1": bm25_value,
        "embedding_v0.1": embedding_value,
        "hybrid_v0.1": hybrid_value,
        "hybrid_minus_bm25": hybrid_minus_bm25,
        "hybrid_minus_embedding": hybrid_minus_embedding,
    }


def build_three_way_comparison_rows(
    bm25_scores: dict[str, Any],
    bm25_per_question: Sequence[dict[str, Any]],
    embedding_scores: dict[str, Any],
    embedding_per_question: Sequence[dict[str, Any]],
    hybrid_scores: dict[str, Any],
    hybrid_per_question: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare all frozen metrics for BM25, embedding, and hybrid."""
    for label, scores in (
        ("BM25", bm25_scores),
        ("embedding", embedding_scores),
        ("hybrid", hybrid_scores),
    ):
        if scores.get("k_values") != list(K_VALUES):
            raise EvaluationError(f"{label} scores do not contain the frozen K values")
    rows: list[dict[str, Any]] = []
    metric_groups = (
        ("evidence", "evidence_metrics", EVIDENCE_COMPARISON_METRICS),
        ("numeric", "numeric_metrics", NUMERIC_COMPARISON_METRICS),
    )
    for domain, score_key, metrics in metric_groups:
        for k in K_VALUES:
            system_values = tuple(
                scores[score_key][str(k)]
                for scores in (bm25_scores, embedding_scores, hybrid_scores)
            )
            for metric, field in metrics:
                rows.append(
                    _three_way_comparison_row(
                        "aggregate", domain, "", k, metric,
                        *(values[field] for values in system_values),
                    )
                )

    per_question_maps = []
    for system_rows in (
        bm25_per_question, embedding_per_question, hybrid_per_question,
    ):
        per_question_maps.append({
            (row["domain"], row["q_id"], int(row["k"])): row
            for row in system_rows
        })
    if not (
        set(per_question_maps[0])
        == set(per_question_maps[1])
        == set(per_question_maps[2])
    ):
        raise EvaluationError("per-question comparison keys differ between systems")
    per_question_fields = {
        "evidence": EVIDENCE_COMPARISON_METRICS,
        "numeric": tuple(
            (
                metric,
                "numeric_question_complete"
                if field == "numeric_question_complete_rate"
                else field,
            )
            for metric, field in NUMERIC_COMPARISON_METRICS
        ),
    }
    for domain, q_id, k in sorted(per_question_maps[0]):
        system_rows = tuple(
            mapping[(domain, q_id, k)] for mapping in per_question_maps
        )
        for metric, field in per_question_fields[domain]:
            rows.append(
                _three_way_comparison_row(
                    "per_question", domain, q_id, k, metric,
                    *(row[field] for row in system_rows),
                )
            )
    return rows


def _four_way_comparison_row(
    scope: str,
    domain: str,
    q_id: str,
    k: int,
    metric: str,
    bm25_value: Any,
    embedding_value: Any,
    hybrid_value: Any,
    reranker_value: Any,
) -> dict[str, Any]:
    values = tuple(
        _comparison_value(value)
        for value in (bm25_value, embedding_value, hybrid_value, reranker_value)
    )
    bm25_value, embedding_value, hybrid_value, reranker_value = values

    def signed_delta(left: Any, right: Any) -> float | str:
        if left == "" or right == "":
            return ""
        return round(float(left) - float(right), 12)

    return {
        "scope": scope,
        "domain": domain,
        "q_id": q_id,
        "k": k,
        "metric": metric,
        "bm25_v0.1": bm25_value,
        "embedding_v0.1": embedding_value,
        "hybrid_v0.1": hybrid_value,
        "reranker_v0.1": reranker_value,
        "hybrid_minus_bm25": signed_delta(hybrid_value, bm25_value),
        "hybrid_minus_embedding": signed_delta(hybrid_value, embedding_value),
        "reranker_minus_bm25": signed_delta(reranker_value, bm25_value),
        "reranker_minus_embedding": signed_delta(reranker_value, embedding_value),
        "reranker_minus_hybrid": signed_delta(reranker_value, hybrid_value),
    }


def build_four_way_comparison_rows(
    bm25_scores: dict[str, Any],
    bm25_per_question: Sequence[dict[str, Any]],
    embedding_scores: dict[str, Any],
    embedding_per_question: Sequence[dict[str, Any]],
    hybrid_scores: dict[str, Any],
    hybrid_per_question: Sequence[dict[str, Any]],
    reranker_scores: dict[str, Any],
    reranker_per_question: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare all frozen metrics for the four frozen retrieval systems."""
    systems = (
        ("BM25", bm25_scores),
        ("embedding", embedding_scores),
        ("hybrid", hybrid_scores),
        ("reranker", reranker_scores),
    )
    for label, scores in systems:
        if scores.get("k_values") != list(K_VALUES):
            raise EvaluationError(f"{label} scores do not contain the frozen K values")

    rows: list[dict[str, Any]] = []
    metric_groups = (
        ("evidence", "evidence_metrics", EVIDENCE_COMPARISON_METRICS),
        ("numeric", "numeric_metrics", NUMERIC_COMPARISON_METRICS),
    )
    for domain, score_key, metrics in metric_groups:
        for k in K_VALUES:
            system_values = tuple(scores[score_key][str(k)] for _, scores in systems)
            for metric, field in metrics:
                rows.append(
                    _four_way_comparison_row(
                        "aggregate", domain, "", k, metric,
                        *(values[field] for values in system_values),
                    )
                )

    per_question_maps = []
    for system_rows in (
        bm25_per_question,
        embedding_per_question,
        hybrid_per_question,
        reranker_per_question,
    ):
        per_question_maps.append({
            (row["domain"], row["q_id"], int(row["k"])): row
            for row in system_rows
        })
    if not all(
        set(mapping) == set(per_question_maps[0])
        for mapping in per_question_maps[1:]
    ):
        raise EvaluationError("per-question comparison keys differ between systems")
    per_question_fields = {
        "evidence": EVIDENCE_COMPARISON_METRICS,
        "numeric": tuple(
            (
                metric,
                "numeric_question_complete"
                if field == "numeric_question_complete_rate"
                else field,
            )
            for metric, field in NUMERIC_COMPARISON_METRICS
        ),
    }
    for domain, q_id, k in sorted(per_question_maps[0]):
        system_rows = tuple(
            mapping[(domain, q_id, k)] for mapping in per_question_maps
        )
        for metric, field in per_question_fields[domain]:
            rows.append(
                _four_way_comparison_row(
                    "per_question", domain, q_id, k, metric,
                    *(row[field] for row in system_rows),
                )
            )
    return rows


def run(
    gold_dir: Path = GOLD_DIR,
    query_path: Path = QUERY_PATH,
    result_path: Path = RESULT_PATH,
    scores_path: Path = SCORES_PATH,
    per_question_path: Path = PER_QUESTION_PATH,
    misses_path: Path = MISSES_PATH,
    comparison_path: Path | None = None,
) -> dict[str, str]:
    """Evaluate and write deterministic artifacts, guarding the frozen result."""
    frozen_before = sha256_file(result_path)
    protected = {path.resolve() for path in (result_path, query_path)} | {
        path.resolve() for path in gold_dir.glob("*.json")
    }
    outputs = [scores_path, per_question_path, misses_path]
    if comparison_path is not None:
        outputs.append(comparison_path)
    for output in outputs:
        if output.resolve() in protected:
            raise EvaluationError(f"refusing to overwrite frozen input: {output}")
    scores, per_question, misses = evaluate(
        gold_dir=gold_dir, query_path=query_path, result_path=result_path
    )
    _write_json(scores_path, scores)
    _write_csv(per_question_path, PER_QUESTION_FIELDS, per_question)
    _write_csv(misses_path, MISS_FIELDS, misses)
    if comparison_path is not None:
        bm25_scores, bm25_per_question, _ = evaluate(
            gold_dir=gold_dir,
            query_path=query_path,
            result_path=RESULT_PATH,
            system=BM25_SYSTEM,
        )
        if scores["bindings"].get("embedding_version") == EMBEDDING_SYSTEM.version:
            comparison_rows = build_comparison_rows(
                bm25_scores,
                bm25_per_question,
                scores,
                per_question,
            )
            _write_csv(comparison_path, COMPARISON_FIELDS, comparison_rows)
        elif scores["bindings"].get("hybrid_version") == HYBRID_SYSTEM.version:
            embedding_scores, embedding_per_question, _ = evaluate(
                gold_dir=gold_dir,
                query_path=query_path,
                result_path=ROOT / "evaluation" / "results" / "embedding_v0.1.jsonl",
                system=EMBEDDING_SYSTEM,
            )
            comparison_rows = build_three_way_comparison_rows(
                bm25_scores,
                bm25_per_question,
                embedding_scores,
                embedding_per_question,
                scores,
                per_question,
            )
            _write_csv(
                comparison_path, THREE_WAY_COMPARISON_FIELDS, comparison_rows
            )
        elif scores["bindings"].get("reranker_version") == RERANKER_SYSTEM.version:
            embedding_scores, embedding_per_question, _ = evaluate(
                gold_dir=gold_dir,
                query_path=query_path,
                result_path=ROOT / "evaluation" / "results" / "embedding_v0.1.jsonl",
                system=EMBEDDING_SYSTEM,
            )
            hybrid_scores, hybrid_per_question, _ = evaluate(
                gold_dir=gold_dir,
                query_path=query_path,
                result_path=ROOT / "evaluation" / "results" / "hybrid_v0.1.jsonl",
                system=HYBRID_SYSTEM,
            )
            comparison_rows = build_four_way_comparison_rows(
                bm25_scores,
                bm25_per_question,
                embedding_scores,
                embedding_per_question,
                hybrid_scores,
                hybrid_per_question,
                scores,
                per_question,
            )
            _write_csv(
                comparison_path, FOUR_WAY_COMPARISON_FIELDS, comparison_rows
            )
        else:
            raise EvaluationError(
                "comparison output requires embedding_v0.1, hybrid_v0.1, "
                "or reranker_v0.1 results"
            )
    frozen_after = sha256_file(result_path)
    if frozen_after != frozen_before:
        raise EvaluationError("frozen ranked-result artifact changed during scoring")
    return {str(path): sha256_file(path) for path in outputs}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD_DIR)
    parser.add_argument("--queries", type=Path, default=QUERY_PATH)
    parser.add_argument("--results", type=Path, default=RESULT_PATH)
    parser.add_argument("--scores", type=Path, default=SCORES_PATH)
    parser.add_argument("--per-question", type=Path, default=PER_QUESTION_PATH)
    parser.add_argument("--misses", type=Path, default=MISSES_PATH)
    parser.add_argument("--comparison", type=Path)
    args = parser.parse_args(argv)
    hashes = run(
        gold_dir=args.gold_dir,
        query_path=args.queries,
        result_path=args.results,
        scores_path=args.scores,
        per_question_path=args.per_question,
        misses_path=args.misses,
        comparison_path=args.comparison,
    )
    for path, digest in hashes.items():
        print(f"{digest}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
