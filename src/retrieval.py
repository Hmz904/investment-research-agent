"""Deterministic lexical BM25 retrieval over ingested SEC chunks.

Tokenization is intentionally small and auditable: input is Unicode NFKC
normalized, common dash/apostrophe variants are canonicalized, text is
case-folded, and lexical alphanumeric terms are extracted. Hyphenated,
slash-separated, apostrophe-containing, decimal, percentage, and
comma-grouped numeric terms are preserved; grouping commas are removed.
No stemming, stop-word removal, aliases, or semantic expansion is applied.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


BM25_IMPLEMENTATION = "thesisagent_direct_bm25"
BM25_IMPLEMENTATION_VERSION = "1"
TOKENIZER_VERSION = "sec_lexical_v1"
DEFAULT_K1 = 1.5
DEFAULT_B = 0.75

_CHAR_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
    }
)
_TOKEN_RE = re.compile(
    r"(?u)(?<!\w)\d{1,3}(?:,\d{3})+(?:\.\d+)?%?(?!\w)"
    r"|[^\W_]+(?:[-/'’][^\W_]+)*(?:\.\d+)?%?"
)

_METADATA_FIELDS = (
    "company",
    "form",
    "filing_date",
    "period_of_report",
    "fiscal_period",
    "calendar_period",
    "source_role",
    "doc_role",
    "exhibit_number",
    "block_type",
)


def tokenize(text: str) -> list[str]:
    """Return deterministic SEC-oriented lexical tokens for *text*."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", str(text))
    normalized = normalized.translate(_CHAR_TRANSLATION).casefold()
    return [match.group(0).replace(",", "") for match in _TOKEN_RE.finditer(normalized)]


def tokenizer_config() -> dict[str, Any]:
    """Return the stable, serializable tokenizer configuration."""
    return {
        "version": TOKENIZER_VERSION,
        "unicode_normalization": "NFKC",
        "case_normalization": "casefold",
        "grouping_commas": "removed_within_numeric_tokens",
        "preserved_compounds": ["hyphen", "slash", "apostrophe"],
        "preserved_numeric_forms": ["decimal", "percentage"],
        "stemming": False,
        "stop_words": False,
        "semantic_expansion": False,
    }


@dataclass(frozen=True)
class CorpusSnapshot:
    """An immutable view of canonical ingested chunk records."""

    records: tuple[dict[str, Any], ...]
    corpus_fingerprint: str
    ingestion_schema_version: str


@dataclass(frozen=True)
class _IndexedDocument:
    chunk_id: str
    doc_id: str
    accession: str
    company: str | None
    form: str | None
    filing_date: str | None
    period_of_report: str | None
    fiscal_period: str | None
    calendar_period: str | None
    source_role: str | None
    doc_role: str | None
    exhibit_number: str | None
    block_type: str | None
    section_path: tuple[str, ...]
    chunk_text: str
    retrieval_text: str

    def metadata_value(self, key: str) -> Any:
        if key == "section_path":
            return self.section_path
        if key in _METADATA_FIELDS or key in {"chunk_id", "doc_id", "accession"}:
            return getattr(self, key)
        raise ValueError(f"unsupported metadata filter: {key}")


@dataclass(frozen=True)
class SearchResult:
    """One ranked BM25 result with canonical chunk and filing metadata."""

    rank: int
    score: float
    chunk_id: str
    doc_id: str
    accession: str
    company: str | None
    form: str | None
    filing_date: str | None
    period_of_report: str | None
    fiscal_period: str | None
    calendar_period: str | None
    source_role: str | None
    doc_role: str | None
    exhibit_number: str | None
    block_type: str | None
    section_path: tuple[str, ...]
    chunk_text: str
    retrieval_text: str

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.__dict__)
        payload["section_path"] = list(self.section_path)
        return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_ingested_corpus(
    data_dir: str | Path,
    *,
    expected_corpus_fingerprint: str | None = None,
    expected_ingestion_schema_version: str | None = None,
    verify_chunk_hashes: bool = True,
) -> CorpusSnapshot:
    """Load canonical chunks and join filing metadata from ingestion.

    Input files are only read. Returned records are newly allocated and sorted
    by ``chunk_id`` so ingestion document order cannot affect indexing.
    """
    root = Path(data_dir)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fingerprint = str(manifest.get("corpus_fingerprint", ""))
    schema_version = str(manifest.get("ingestion_schema_version", ""))
    if expected_corpus_fingerprint is not None and fingerprint != expected_corpus_fingerprint:
        raise ValueError(
            "corpus fingerprint mismatch: "
            f"expected={expected_corpus_fingerprint} actual={fingerprint}"
        )
    if (
        expected_ingestion_schema_version is not None
        and schema_version != expected_ingestion_schema_version
    ):
        raise ValueError(
            "ingestion schema mismatch: "
            f"expected={expected_ingestion_schema_version} actual={schema_version}"
        )

    records: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    entries = sorted(manifest.get("entries", []), key=lambda item: str(item["doc_id"]))
    for entry in entries:
        doc_id = str(entry["doc_id"])
        chunks_path = root / "chunks" / f"{doc_id}.json"
        if verify_chunk_hashes:
            expected_hash = str(entry.get("chunk_sha256", ""))
            actual_hash = _sha256(chunks_path)
            if not expected_hash or actual_hash != expected_hash:
                raise ValueError(
                    f"chunk artifact hash mismatch for {doc_id}: "
                    f"expected={expected_hash} actual={actual_hash}"
                )
        payload = json.loads(chunks_path.read_text(encoding="utf-8"))
        if str(payload.get("doc_id", "")) != doc_id:
            raise ValueError(f"chunk artifact doc_id mismatch for {doc_id}")
        for source_chunk in payload.get("chunks", []):
            record = copy.deepcopy(source_chunk)
            if str(record.get("doc_id", "")) != doc_id:
                raise ValueError(f"chunk doc_id mismatch in {chunks_path}")
            chunk_id = str(record.get("chunk_id", ""))
            if not chunk_id:
                raise ValueError(f"missing chunk_id in {chunks_path}")
            if chunk_id in seen_chunk_ids:
                raise ValueError(f"duplicate chunk_id: {chunk_id}")
            seen_chunk_ids.add(chunk_id)
            for field in _METADATA_FIELDS:
                if field == "block_type":
                    continue
                if field in entry:
                    record[field] = copy.deepcopy(entry[field])
            records.append(record)

    records.sort(key=lambda item: str(item["chunk_id"]))
    return CorpusSnapshot(
        records=tuple(records),
        corpus_fingerprint=fingerprint,
        ingestion_schema_version=schema_version,
    )


class BM25Retriever:
    """A deterministic in-memory Okapi BM25 index."""

    def __init__(self, *, k1: float = DEFAULT_K1, b: float = DEFAULT_B) -> None:
        if k1 < 0:
            raise ValueError("k1 must be non-negative")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self.k1 = float(k1)
        self.b = float(b)
        self._documents: tuple[_IndexedDocument, ...] = ()
        self._document_lengths: tuple[int, ...] = ()
        self._postings: dict[str, tuple[tuple[int, int], ...]] = {}
        self._document_frequency: dict[str, int] = {}
        self._average_document_length = 0.0
        self._index_fingerprint = ""

    @property
    def index_fingerprint(self) -> str:
        self._require_index()
        return self._index_fingerprint

    @property
    def indexed_chunk_count(self) -> int:
        return len(self._documents)

    @property
    def vocabulary_size(self) -> int:
        return len(self._postings)

    @property
    def statistics(self) -> dict[str, int | float | str]:
        self._require_index()
        lengths = self._document_lengths
        return {
            "indexed_chunk_count": len(lengths),
            "vocabulary_size": len(self._postings),
            "average_document_length": self._average_document_length,
            "min_document_length": min(lengths, default=0),
            "max_document_length": max(lengths, default=0),
            "index_fingerprint": self._index_fingerprint,
        }

    @property
    def config(self) -> dict[str, Any]:
        return {
            "implementation": BM25_IMPLEMENTATION,
            "implementation_version": BM25_IMPLEMENTATION_VERSION,
            "k1": self.k1,
            "b": self.b,
            "idf": "log(1 + (N - df + 0.5) / (df + 0.5))",
            "query_term_frequency": "unique_terms",
            "tokenizer": tokenizer_config(),
        }

    def build_index(self, records: Iterable[Mapping[str, Any]]) -> None:
        """Build an index from canonical ingestion records without mutation."""
        source_records = sorted(records, key=lambda item: str(item.get("chunk_id", "")))
        documents: list[_IndexedDocument] = []
        token_lists: list[list[str]] = []
        seen: set[str] = set()

        for source in source_records:
            chunk_id = str(source.get("chunk_id", ""))
            doc_id = str(source.get("doc_id", ""))
            accession = str(source.get("accession", ""))
            if not chunk_id or not doc_id or not accession:
                raise ValueError("each record requires chunk_id, doc_id, and accession")
            if chunk_id in seen:
                raise ValueError(f"duplicate chunk_id: {chunk_id}")
            seen.add(chunk_id)

            chunk_text = str(source.get("text") or "")
            retrieval_value = source.get("retrieval_text")
            retrieval_text = (
                str(retrieval_value) if retrieval_value is not None else chunk_text
            )
            raw_section_path = source.get("section_path") or ()
            if isinstance(raw_section_path, str):
                section_path = (raw_section_path,)
            else:
                section_path = tuple(str(part) for part in raw_section_path)

            def optional_text(field: str) -> str | None:
                value = source.get(field)
                return None if value is None else str(value)

            documents.append(
                _IndexedDocument(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    accession=accession,
                    company=optional_text("company"),
                    form=optional_text("form"),
                    filing_date=optional_text("filing_date"),
                    period_of_report=optional_text("period_of_report"),
                    fiscal_period=optional_text("fiscal_period"),
                    calendar_period=optional_text("calendar_period"),
                    source_role=optional_text("source_role"),
                    doc_role=optional_text("doc_role"),
                    exhibit_number=optional_text("exhibit_number"),
                    block_type=optional_text("block_type"),
                    section_path=section_path,
                    chunk_text=chunk_text,
                    retrieval_text=retrieval_text,
                )
            )
            token_lists.append(tokenize(retrieval_text))

        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for document_index, tokens in enumerate(token_lists):
            for term, frequency in sorted(Counter(tokens).items()):
                postings[term].append((document_index, frequency))

        self._documents = tuple(documents)
        self._document_lengths = tuple(len(tokens) for tokens in token_lists)
        self._postings = {term: tuple(items) for term, items in sorted(postings.items())}
        self._document_frequency = {
            term: len(items) for term, items in self._postings.items()
        }
        self._average_document_length = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 0.0
        )
        self._index_fingerprint = self._fingerprint(token_lists)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return ranked matching chunks, optionally exact-filtered by metadata."""
        self._require_index()
        if not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k <= 0:
            return []
        terms = tuple(dict.fromkeys(tokenize(query)))
        if not terms:
            return []

        active_filters = dict(filters or {})
        for key in active_filters:
            if key not in _METADATA_FIELDS and key not in {
                "section_path", "chunk_id", "doc_id", "accession"
            }:
                raise ValueError(f"unsupported metadata filter: {key}")

        scores: dict[int, float] = defaultdict(float)
        document_count = len(self._documents)
        average_length = self._average_document_length
        for term in terms:
            postings = self._postings.get(term)
            if not postings:
                continue
            document_frequency = self._document_frequency[term]
            inverse_document_frequency = math.log1p(
                (document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            for document_index, term_frequency in postings:
                document = self._documents[document_index]
                if not self._matches_filters(document, active_filters):
                    continue
                document_length = self._document_lengths[document_index]
                length_ratio = document_length / average_length if average_length else 0.0
                denominator = term_frequency + self.k1 * (
                    1.0 - self.b + self.b * length_ratio
                )
                if denominator:
                    scores[document_index] += inverse_document_frequency * (
                        term_frequency * (self.k1 + 1.0) / denominator
                    )

        ranked = sorted(
            scores.items(),
            key=lambda item: (-item[1], self._documents[item[0]].chunk_id),
        )[:top_k]
        return [
            self._result(rank, score, self._documents[document_index])
            for rank, (document_index, score) in enumerate(ranked, start=1)
        ]

    def _matches_filters(
        self, document: _IndexedDocument, filters: Mapping[str, Any]
    ) -> bool:
        return all(document.metadata_value(key) == value for key, value in filters.items())

    def _result(
        self, rank: int, score: float, document: _IndexedDocument
    ) -> SearchResult:
        return SearchResult(rank=rank, score=score, **document.__dict__)

    def _fingerprint(self, token_lists: Sequence[Sequence[str]]) -> str:
        digest = hashlib.sha256()
        header = json.dumps(
            self.config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(header).to_bytes(8, "big"))
        digest.update(header)
        for document, tokens in zip(self._documents, token_lists, strict=True):
            indexed_record = {
                **document.__dict__,
                "section_path": list(document.section_path),
                "tokens": list(tokens),
            }
            encoded = json.dumps(
                indexed_record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return digest.hexdigest()

    def _require_index(self) -> None:
        if not self._index_fingerprint:
            raise RuntimeError("build_index must be called before retrieval")
