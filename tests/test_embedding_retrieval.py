"""Gold-blind unit tests for deterministic dense retrieval."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence

import numpy as np
import pytest

from src.embedding_retrieval import (
    DenseRetriever,
    normalize_embeddings,
    stable_json_line,
)


class FakeEncoder:
    def __init__(
        self,
        vectors: Mapping[str, Sequence[float]],
        *,
        identity: str = "fake-v1",
        max_sequence_length: int = 8,
    ) -> None:
        self.vectors = {key: list(value) for key, value in vectors.items()}
        self.identity = identity
        self._dimension = len(next(iter(self.vectors.values())))
        self._max_sequence_length = max_sequence_length
        self.encode_calls = 0

    @property
    def config(self) -> Mapping[str, object]:
        return {
            "model_id": "fake",
            "model_revision": self.identity,
            "embedding_dimension": self._dimension,
            "model_max_sequence_length": self._max_sequence_length,
            "pooling": "fake_pooling",
            "normalization": "l2",
            "similarity": "dot_product_over_l2_normalized_vectors",
            "tokenizer": {"fingerprint": self.identity},
        }

    @property
    def embedding_dimension(self) -> int:
        return self._dimension

    @property
    def max_sequence_length(self) -> int:
        return self._max_sequence_length

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        self.encode_calls += 1
        return np.asarray([self.vectors[text] for text in texts], dtype=np.float64)

    def token_lengths(self, texts: Sequence[str]) -> list[int]:
        return [len(text.split()) + 2 for text in texts]


def _record(chunk_id: str, text: str, **metadata: object) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": metadata.pop("doc_id", f"DOC-{chunk_id}"),
        "accession": metadata.pop("accession", f"ACC-{chunk_id}"),
        "section_path": metadata.pop("section_path", ["Item 1"]),
        "text": text,
        **metadata,
    }


def _retriever(
    vectors: Mapping[str, Sequence[float]],
    records: Sequence[Mapping[str, object]],
    **kwargs: object,
) -> DenseRetriever:
    retriever = DenseRetriever(FakeEncoder(vectors), **kwargs)
    retriever.build_index(records, corpus_fingerprint="corpus")
    return retriever


def test_l2_normalization_is_float32_and_row_wise() -> None:
    normalized = normalize_embeddings(np.asarray([[3.0, 4.0], [0.0, 2.0]]))
    assert normalized.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(normalized, axis=1), [1.0, 1.0])
    np.testing.assert_allclose(normalized[0], [0.6, 0.8])
    with pytest.raises(ValueError, match="zero"):
        normalize_embeddings(np.zeros((1, 2)))


def test_cosine_dot_product_ranking_semantics() -> None:
    retriever = _retriever(
        {"axis": [9, 0], "diagonal": [1, 1], "query": [3, 0]},
        [_record("axis", "axis"), _record("diagonal", "diagonal")],
    )
    results = retriever.search("query")
    assert [result.chunk_id for result in results] == ["axis", "diagonal"]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(2**-0.5)


def test_ranking_and_chunk_id_tie_break_are_deterministic() -> None:
    vectors = {"same-a": [1, 0], "same-z": [2, 0], "query": [1, 0]}
    records = [_record("z", "same-z"), _record("a", "same-a")]
    first = _retriever(vectors, records)
    second = _retriever(vectors, list(reversed(records)))
    assert [result.chunk_id for result in first.search("query")] == ["a", "z"]
    assert [result.to_dict() for result in first.search("query")] == [
        result.to_dict() for result in second.search("query")
    ]
    assert first.index_fingerprint == second.index_fingerprint


def test_top_k_and_empty_query_behavior() -> None:
    vectors = {"a": [1, 0], "b": [0, 1], "query": [1, 0]}
    encoder = FakeEncoder(vectors)
    retriever = DenseRetriever(encoder)
    retriever.build_index([_record("a", "a"), _record("b", "b")], corpus_fingerprint="c")
    calls_after_index = encoder.encode_calls
    assert len(retriever.search("query", top_k=1)) == 1
    assert retriever.search("query", top_k=0) == []
    assert retriever.search("") == []
    assert retriever.search("   ") == []
    assert encoder.encode_calls == calls_after_index + 1
    with pytest.raises(TypeError, match="top_k"):
        retriever.search("query", top_k=1.5)  # type: ignore[arg-type]


def test_retrieval_text_and_metadata_are_propagated() -> None:
    retriever = _retriever(
        {"indexed": [1, 0], "query": [1, 0]},
        [
            _record(
                "chunk-1",
                "canonical",
                retrieval_text="indexed",
                doc_id="DOC",
                accession="0001",
                company="Example Co",
                form="10-Q",
                filing_date="2026-04-30",
                period_of_report="2026-03-31",
                fiscal_period="FY26Q1",
                calendar_period="2026Q1",
                source_role="benchmark_period",
                doc_role="primary",
                block_type="table",
                section_path=["Part I", "Item 2"],
            )
        ],
    )
    result = retriever.search("query")[0]
    assert result.chunk_text == "canonical"
    assert result.retrieval_text == "indexed"
    assert result.doc_id == "DOC"
    assert result.accession == "0001"
    assert result.company == "Example Co"
    assert result.form == "10-Q"
    assert result.filing_date == "2026-04-30"
    assert result.period_of_report == "2026-03-31"
    assert result.section_path == ("Part I", "Item 2")


def test_build_and_search_do_not_mutate_source_records() -> None:
    records = [
        _record(
            "table",
            "source text",
            section_path=["Note 1"],
            table_json={"rows": [{"cells": [{"raw_text": "Revenue"}]}]},
            retrieval_text="indexed",
        )
    ]
    before = copy.deepcopy(records)
    retriever = _retriever(
        {"indexed": [1, 0], "query": [1, 0]},
        records,
    )
    retriever.search("query")
    assert records == before


def test_cache_hits_and_text_or_config_changes_invalidate(tmp_path) -> None:
    cache = tmp_path / "cache"
    records = [_record("a", "alpha")]
    first_encoder = FakeEncoder({"alpha": [3, 4]}, identity="one")
    first = DenseRetriever(first_encoder, cache_dir=cache)
    first.build_index(records, corpus_fingerprint="corpus")
    assert first.cache_status == "miss"
    assert first_encoder.encode_calls == 1

    second_encoder = FakeEncoder({"alpha": [99, 1]}, identity="one")
    second = DenseRetriever(second_encoder, cache_dir=cache)
    second.build_index(records, corpus_fingerprint="corpus")
    assert second.cache_status == "hit"
    assert second_encoder.encode_calls == 0
    assert second.index_fingerprint == first.index_fingerprint

    changed_text = FakeEncoder({"changed": [1, 2]}, identity="one")
    third = DenseRetriever(changed_text, cache_dir=cache)
    third.build_index([_record("a", "changed")], corpus_fingerprint="corpus")
    assert third.cache_status == "miss"
    assert changed_text.encode_calls == 1

    changed_config = FakeEncoder({"changed": [1, 2]}, identity="two")
    fourth = DenseRetriever(changed_config, cache_dir=cache)
    fourth.build_index([_record("a", "changed")], corpus_fingerprint="corpus")
    assert fourth.cache_status == "miss"
    assert changed_config.encode_calls == 1


def test_index_metadata_is_complete_and_json_serializable() -> None:
    retriever = _retriever({"alpha": [3, 4]}, [_record("a", "alpha")])
    metadata = retriever.index_metadata
    assert metadata["embedding_dimension"] == 2
    assert metadata["embedding_matrix_dtype"] == "float32"
    assert metadata["corpus_fingerprint"] == "corpus"
    assert len(metadata["ordered_chunk_id_fingerprint"]) == 64
    assert len(metadata["indexed_text_fingerprint"]) == 64
    assert len(metadata["embedding_matrix_sha256"]) == 64
    assert json.loads(stable_json_line(metadata)) == metadata


def test_truncation_diagnostics_use_pre_truncation_lengths() -> None:
    encoder = FakeEncoder(
        {"one two": [1, 0], "one two three four": [0, 1]},
        max_sequence_length=5,
    )
    retriever = DenseRetriever(encoder)
    retriever.build_index(
        [_record("a", "one two"), _record("b", "one two three four")],
        corpus_fingerprint="corpus",
    )
    diagnostics = retriever.truncation_diagnostics
    assert diagnostics["chunks_exceeding_model_max"] == 1
    assert diagnostics["percent_exceeding_model_max"] == 50.0
    assert diagnostics["median_token_length"] == 5.0
    assert diagnostics["max_token_length"] == 6


def test_result_serialization_is_stable() -> None:
    retriever = _retriever(
        {"alpha": [1, 0], "query": [1, 0]},
        [_record("a", "alpha")],
    )
    payload = {"result": retriever.search("query")[0].to_dict(), "method": "dense"}
    first = stable_json_line(payload)
    second = stable_json_line(dict(reversed(list(payload.items()))))
    assert first == second
    assert first.endswith("\n")
    assert ": " not in first
    assert ", " not in first
