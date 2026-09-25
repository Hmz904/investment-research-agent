"""Gold-blind unit tests for RetrievalTool v0.1."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.reranker_retrieval import PairScore
from src.tools.retrieval_tool import (
    CANDIDATE_DEPTH,
    EMBEDDING_MODEL_REVISION,
    EXPECTED_CORPUS_FINGERPRINT,
    RetrievalArtifactError,
    RetrievalInputError,
    RetrievalMetadataError,
    RetrievalModelRevisionError,
    RetrievalTool,
    RetrievalUpstreamError,
    canonical_trace_json,
)


def _record(index: int, **overrides: object) -> dict[str, object]:
    chunk_id = str(overrides.pop("chunk_id", f"chunk-{index:03d}"))
    return {
        "chunk_id": chunk_id,
        "doc_id": overrides.pop("doc_id", f"DOC-{index // 10}"),
        "accession": overrides.pop("accession", f"0000000000-00-{index:06d}"),
        "company": overrides.pop("company", "Example"),
        "form": overrides.pop("form", "10-Q"),
        "filing_date": overrides.pop("filing_date", "2026-01-01"),
        "period_of_report": overrides.pop("period_of_report", "2025-12-31"),
        "fiscal_period": overrides.pop("fiscal_period", "FY26Q1"),
        "calendar_period": overrides.pop("calendar_period", "2025Q4"),
        "source_role": overrides.pop("source_role", "benchmark_period"),
        "doc_role": overrides.pop("doc_role", "primary"),
        "exhibit_number": overrides.pop("exhibit_number", ""),
        "block_type": overrides.pop("block_type", "text"),
        "section_path": overrides.pop("section_path", ["Part I", "Item 2"]),
        "char_start": overrides.pop("char_start", index * 10),
        "char_end": overrides.pop("char_end", index * 10 + 9),
        "text": overrides.pop("text", f"Canonical text {chunk_id}"),
        "retrieval_text": overrides.pop("retrieval_text", f"Passage {chunk_id}"),
        **overrides,
    }


def _candidate(record: Mapping[str, object], rank: int, score: float) -> dict[str, object]:
    return {
        "rank": rank,
        "score": score,
        "chunk_id": record["chunk_id"],
        "doc_id": record["doc_id"],
        "accession": record["accession"],
        "company": record["company"],
        "form": record["form"],
        "filing_date": record["filing_date"],
        "period_of_report": record["period_of_report"],
        "fiscal_period": record["fiscal_period"],
        "calendar_period": record["calendar_period"],
        "source_role": record["source_role"],
        "doc_role": record["doc_role"],
        "exhibit_number": record["exhibit_number"],
        "block_type": record["block_type"],
        "section_path": list(record["section_path"]),
        "chunk_text": record["text"],
        "retrieval_text": record["retrieval_text"],
    }


class FakeRetriever:
    def __init__(
        self,
        candidates: Sequence[Mapping[str, object]],
        *,
        config: Mapping[str, object] | None = None,
    ) -> None:
        self.candidates = [dict(candidate) for candidate in candidates]
        self.calls: list[tuple[str, int]] = []
        self._config = dict(config or {})

    @property
    def config(self) -> Mapping[str, object]:
        return self._config

    def search(self, query: str, *, top_k: int) -> Sequence[Mapping[str, object]]:
        self.calls.append((query, top_k))
        return self.candidates[:top_k]


class FakeReranker:
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"

    def __init__(self, scores: Mapping[str, float] | None = None) -> None:
        self.scores = dict(scores or {})
        self.seen_candidate_ids: list[str] = []
        self.seen_candidate_batches: list[tuple[str, ...]] = []

    def score_candidates(
        self,
        query_en: str,
        candidates: Sequence[Mapping[str, object]],
    ) -> list[PairScore]:
        self.seen_candidate_ids = [str(candidate["chunk_id"]) for candidate in candidates]
        self.seen_candidate_batches.append(tuple(self.seen_candidate_ids))
        return [
            PairScore(
                chunk_id=str(candidate["chunk_id"]),
                score=self.scores.get(str(candidate["chunk_id"]), 0.0),
                original_token_count=10,
                retained_token_count=10,
                original_passage_token_count=5,
                retained_passage_token_count=5,
                passage_truncated=False,
            )
            for candidate in candidates
        ]


class OutsideUnionReranker(FakeReranker):
    def score_candidates(
        self,
        query_en: str,
        candidates: Sequence[Mapping[str, object]],
    ) -> list[PairScore]:
        scores = super().score_candidates(query_en, candidates)
        return [*scores[:-1], PairScore("outside", 1.0, 10, 10, 5, 5, False)]


def _tool(
    *,
    bm25_indices: range = range(0, 50),
    embedding_indices: range = range(25, 75),
    scores: Mapping[str, float] | None = None,
    records: Sequence[Mapping[str, object]] | None = None,
) -> tuple[RetrievalTool, FakeRetriever, FakeRetriever, FakeReranker]:
    corpus = list(records or [_record(index) for index in range(75)])
    by_id = {str(record["chunk_id"]): record for record in corpus}
    bm25_candidates = [
        _candidate(by_id[f"chunk-{index:03d}"], rank, float(100 - rank))
        for rank, index in enumerate(bm25_indices, start=1)
    ]
    embedding_candidates = [
        _candidate(by_id[f"chunk-{index:03d}"], rank, float(100 - rank))
        for rank, index in enumerate(embedding_indices, start=1)
    ]
    bm25 = FakeRetriever(bm25_candidates)
    embedding = FakeRetriever(
        embedding_candidates,
        config={
            "model_id": "BAAI/bge-base-en-v1.5",
            "model_revision": EMBEDDING_MODEL_REVISION,
        },
    )
    reranker = FakeReranker(scores)
    tool = RetrievalTool(
        bm25_retriever=bm25,
        embedding_retriever=embedding,
        reranker=reranker,
        corpus_records=corpus,
        corpus_fingerprint=EXPECTED_CORPUS_FINGERPRINT,
    )
    return tool, bm25, embedding, reranker


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_empty_query_is_rejected(query: str) -> None:
    tool, *_ = _tool()
    with pytest.raises(RetrievalInputError, match="non-empty"):
        tool.search(query)


@pytest.mark.parametrize("top_k", [0, -1, 51, True, 1.5])
def test_invalid_top_k_is_rejected(top_k: object) -> None:
    tool, *_ = _tool()
    with pytest.raises(RetrievalInputError, match="top_k"):
        tool.search("new query", top_k=top_k)  # type: ignore[arg-type]


def test_exact_union_component_ranks_reranking_and_top_k() -> None:
    scores = {f"chunk-{index:03d}": float(index) for index in range(75)}
    scores["chunk-025"] = 1_000.0
    tool, bm25, embedding, reranker = _tool(scores=scores)
    response = tool.search("new arbitrary query", top_k=10)

    expected_union = {f"chunk-{index:03d}" for index in range(75)}
    assert bm25.calls == [("new arbitrary query", CANDIDATE_DEPTH)]
    assert embedding.calls == [("new arbitrary query", CANDIDATE_DEPTH)]
    assert set(reranker.seen_candidate_ids) == expected_union
    assert response.candidate_pool_size == 75
    assert response.results[0].chunk_id == "chunk-025"
    assert [result.chunk_id for result in response.results[1:]] == [
        f"chunk-{index:03d}" for index in range(74, 65, -1)
    ]
    assert [result.rank for result in response.results] == list(range(1, 11))
    assert [result.reranker_rank for result in response.results] == list(range(1, 11))
    assert all(result.chunk_id in expected_union for result in response.results)
    by_id = {result.chunk_id: result for result in response.results}
    assert by_id["chunk-025"].bm25_rank == 26
    assert by_id["chunk-025"].embedding_rank == 1
    assert by_id["chunk-074"].bm25_rank is None
    assert by_id["chunk-074"].embedding_rank == 50
    assert response.trace.bm25_candidate_count == 50
    assert response.trace.embedding_candidate_count == 50
    assert response.trace.union_candidate_count == 75
    assert response.trace.returned_count == 10


def test_public_top_k_only_changes_final_truncation() -> None:
    scores = {f"chunk-{index:03d}": float(index) for index in range(75)}
    tool, bm25, embedding, reranker = _tool(scores=scores)

    top_five = tool.search("same query", top_k=5)
    top_twenty = tool.search("same query", top_k=20)

    assert bm25.calls == [
        ("same query", CANDIDATE_DEPTH),
        ("same query", CANDIDATE_DEPTH),
    ]
    assert embedding.calls == [
        ("same query", CANDIDATE_DEPTH),
        ("same query", CANDIDATE_DEPTH),
    ]
    assert len(reranker.seen_candidate_batches) == 2
    assert reranker.seen_candidate_batches[0] == reranker.seen_candidate_batches[1]
    assert len(reranker.seen_candidate_batches[0]) == 75
    assert top_five.candidate_pool_size == top_twenty.candidate_pool_size == 75
    assert [result.chunk_id for result in top_five.results] == [
        result.chunk_id for result in top_twenty.results[:5]
    ]
    assert [result.reranker_rank for result in top_five.results] == list(range(1, 6))
    assert [result.reranker_rank for result in top_twenty.results] == list(range(1, 21))


def test_reranker_exact_score_ties_use_chunk_id() -> None:
    tool, *_ = _tool(scores={})
    response = tool.search("tie query", top_k=4)
    assert [result.chunk_id for result in response.results] == [
        "chunk-000",
        "chunk-001",
        "chunk-002",
        "chunk-003",
    ]


def test_component_with_fewer_matches_is_not_filled_by_a_fallback() -> None:
    tool, _, _, reranker = _tool(
        bm25_indices=range(0, 10),
        embedding_indices=range(0, 50),
    )
    response = tool.search("limited lexical matches", top_k=5)
    assert response.trace.bm25_candidate_count == 10
    assert response.trace.embedding_candidate_count == 50
    assert response.candidate_pool_size == 50
    assert len(reranker.seen_candidate_ids) == 50


def test_citation_fields_locator_and_table_metadata_propagate_from_corpus() -> None:
    records = [_record(index) for index in range(75)]
    records[0] = _record(
        0,
        locator="Authoritative Note 7 locator",
        block_type="table",
        table_json={"caption": "Commitments", "rows": []},
        period_columns=[{"label": "2026"}],
        unit_scale="millions",
        xbrl_facts=[],
    )
    scores = {"chunk-000": 100.0}
    tool, *_ = _tool(records=records, scores=scores)
    result = tool.search("metadata query", top_k=1).results[0]
    assert result.chunk_id == "chunk-000"
    assert result.accession == "0000000000-00-000000"
    assert result.locator == "Authoritative Note 7 locator"
    assert result.text == "Canonical text chunk-000"
    assert result.form_type == "10-Q"
    assert result.table_metadata == {
        "table_json": {"caption": "Commitments", "rows": []},
        "period_columns": [{"label": "2026"}],
        "unit_scale": "millions",
        "xbrl_facts": [],
    }


def test_duplicate_upstream_chunk_is_rejected() -> None:
    tool, bm25, *_ = _tool()
    bm25.candidates[-1] = dict(bm25.candidates[0], rank=50)
    with pytest.raises(RetrievalUpstreamError, match="duplicate BM25 chunk_id"):
        tool.search("duplicate query")


def test_component_metadata_conflict_is_rejected() -> None:
    tool, _, embedding, _ = _tool()
    overlapping = next(
        candidate for candidate in embedding.candidates if candidate["chunk_id"] == "chunk-025"
    )
    overlapping["accession"] = "0000000000-00-999999"
    with pytest.raises(RetrievalMetadataError, match="metadata conflict"):
        tool.search("conflict query")


def test_candidate_metadata_must_match_canonical_corpus() -> None:
    tool, bm25, _, _ = _tool()
    bm25.candidates[0]["chunk_text"] = "mutated text"
    with pytest.raises(RetrievalMetadataError, match="text conflict"):
        tool.search("canonical query")


def test_reranker_cannot_introduce_result_outside_component_union() -> None:
    tool, bm25, embedding, _ = _tool()
    outside = RetrievalTool(
        bm25_retriever=bm25,
        embedding_retriever=embedding,
        reranker=OutsideUnionReranker(),
        corpus_records=[_record(index) for index in range(75)],
        corpus_fingerprint=EXPECTED_CORPUS_FINGERPRINT,
    )
    with pytest.raises(RetrievalUpstreamError, match="outside candidate union"):
        outside.search("outside query")


def test_canonical_trace_serialization_is_stable_and_has_no_timestamp() -> None:
    tool, *_ = _tool(scores={"chunk-000": 10.0})
    trace = tool.search("trace query", top_k=2).trace
    first = canonical_trace_json(trace)
    second = canonical_trace_json(dict(reversed(list(trace.to_dict().items()))))
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first.endswith("\n")
    assert ": " not in first and ", " not in first
    payload = json.loads(first)
    assert payload["returned_chunk_ids"] == ["chunk-000", "chunk-001"]
    assert payload["retrieval_stack_version"] == "retrieval_stack_v0.1"
    assert "timestamp" not in payload
    with pytest.raises(ValueError, match="JSON compliant"):
        canonical_trace_json({"non_finite": float("nan")})


def test_declared_model_revision_mismatch_is_rejected() -> None:
    records = [_record(index) for index in range(75)]
    candidates = [_candidate(records[index], index + 1, 1.0) for index in range(50)]
    bad_dense = FakeRetriever(
        candidates,
        config={
            "model_id": "BAAI/bge-base-en-v1.5",
            "model_revision": "wrong",
        },
    )
    with pytest.raises(RetrievalModelRevisionError, match="revision mismatch"):
        RetrievalTool(
            bm25_retriever=FakeRetriever(candidates),
            embedding_retriever=bad_dense,
            reranker=FakeReranker(),
            corpus_records=records,
            corpus_fingerprint=EXPECTED_CORPUS_FINGERPRINT,
        )


def test_missing_production_artifacts_fail_explicitly(tmp_path: Path) -> None:
    with pytest.raises(RetrievalArtifactError, match="missing corpus manifest"):
        RetrievalTool.from_frozen_stack(
            data_dir=tmp_path / "missing-data",
            embedding_cache_dir=tmp_path / "missing-index",
            model_cache_dir=tmp_path / "missing-model",
        )


def test_frozen_factory_initializes_heavy_resources_once_per_tool_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.tools.retrieval_tool as module

    records = [_record(index) for index in range(75)]
    by_id = {str(record["chunk_id"]): record for record in records}
    bm25_candidates = [
        _candidate(by_id[f"chunk-{index:03d}"], rank, float(100 - rank))
        for rank, index in enumerate(range(0, 50), start=1)
    ]
    dense_candidates = [
        _candidate(by_id[f"chunk-{index:03d}"], rank, float(100 - rank))
        for rank, index in enumerate(range(25, 75), start=1)
    ]
    counts = {
        "corpus_load": 0,
        "bm25_init": 0,
        "bm25_build": 0,
        "dense_init": 0,
        "dense_build": 0,
        "reranker_init": 0,
        "cache_copy": 0,
    }

    def fake_load(*args: object, **kwargs: object) -> SimpleNamespace:
        counts["corpus_load"] += 1
        return SimpleNamespace(
            records=tuple(records),
            corpus_fingerprint=EXPECTED_CORPUS_FINGERPRINT,
        )

    class FactoryBM25(FakeRetriever):
        def __init__(self, **kwargs: object) -> None:
            counts["bm25_init"] += 1
            super().__init__(bm25_candidates)

        def build_index(self, source: Sequence[Mapping[str, object]]) -> None:
            counts["bm25_build"] += 1

    class FactoryDense(FakeRetriever):
        def __init__(self, **kwargs: object) -> None:
            counts["dense_init"] += 1
            super().__init__(
                dense_candidates,
                config={
                    "model_id": "BAAI/bge-base-en-v1.5",
                    "model_revision": EMBEDDING_MODEL_REVISION,
                },
            )
            self.cache_status = "not_built"

        def build_index(
            self,
            source: Sequence[Mapping[str, object]],
            *,
            corpus_fingerprint: str,
        ) -> None:
            counts["dense_build"] += 1
            self.cache_status = "hit"

    class FactoryReranker(FakeReranker):
        def __init__(self, **kwargs: object) -> None:
            counts["reranker_init"] += 1
            super().__init__()

    monkeypatch.setattr(module, "load_ingested_corpus", fake_load)
    monkeypatch.setattr(module, "BM25Retriever", FactoryBM25)
    monkeypatch.setattr(module, "DenseRetriever", FactoryDense)
    monkeypatch.setattr(module, "TransformerCrossEncoder", FactoryReranker)
    monkeypatch.setattr(
        module,
        "model_payload_directory",
        lambda root, model_id, revision: Path(root),
    )
    monkeypatch.setattr(module, "verify_model_payload", lambda *args, **kwargs: None)
    original_copy = module.shutil.copy2

    def counting_copy(source: object, destination: object) -> object:
        counts["cache_copy"] += 1
        return original_copy(source, destination)

    monkeypatch.setattr(module.shutil, "copy2", counting_copy)

    data_dir = tmp_path / "data"
    chunk_dir = data_dir / "chunks"
    embedding_cache = tmp_path / "embedding-cache"
    model_cache = tmp_path / "model-cache"
    chunk_dir.mkdir(parents=True)
    embedding_cache.mkdir()
    model_cache.mkdir()
    (data_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (embedding_cache / "index_metadata.json").write_text("{}", encoding="utf-8")
    (embedding_cache / "embeddings.npy").write_bytes(b"frozen-test-double")

    tool = RetrievalTool.from_frozen_stack(
        data_dir=data_dir,
        embedding_cache_dir=embedding_cache,
        model_cache_dir=model_cache,
    )
    initialized = dict(counts)
    tool.search("first call", top_k=5)
    tool.search("second call", top_k=20)

    assert initialized == {
        "corpus_load": 1,
        "bm25_init": 1,
        "bm25_build": 1,
        "dense_init": 1,
        "dense_build": 1,
        "reranker_init": 1,
        "cache_copy": 2,
    }
    assert counts == initialized


def test_tool_source_has_no_benchmark_gold_or_evaluation_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "src" / "tools" / "retrieval_tool.py").read_text(encoding="utf-8")
    forbidden = (
        "benchmark/" + "dev",
        "benchmark/" + "frozen",
        "numeric_" + "answers",
        "evidence_" + "checklist",
        "score_" + "retrieval",
        "evaluation/" + "results",
    )
    assert all(fragment not in source for fragment in forbidden)
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(
        module == "evaluation"
        or module.startswith("evaluation.")
        or module == "benchmark"
        or module.startswith("benchmark.")
        for module in imported_modules
    )
