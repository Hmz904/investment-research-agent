"""XBRLTool v0.1 over the frozen local inline-XBRL ingestion.

The production factory parses only immutable local filing artifacts through the
existing ingestion parser.  It never contacts SEC or any other network service.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import warnings
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from src.xbrl import parse_inline_xbrl


TOOL_NAME = "XBRLTool"
TOOL_VERSION = "xbrl_tool_v0.1"
XBRL_ARTIFACT_VERSION = "frozen_inline_xbrl_ingestion_v0.1.1"
EXPECTED_INGESTION_SCHEMA_VERSION = "0.1.1"
EXPECTED_CORPUS_FINGERPRINT = (
    "56df698d50b13cf15e913c1c60dbc96b1fd0fab44adb7b1f40ba99771c4b7c96"
)
MAX_TOP_K = 50

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_WORD_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|[A-Z]+|\d+"
)


class XBRLToolError(Exception):
    """Base class for deterministic XBRLTool failures."""


class XBRLInputError(XBRLToolError, ValueError):
    """A tool call violates the public input contract."""


class XBRLArtifactError(XBRLToolError, RuntimeError):
    """A required frozen local artifact is missing or invalid."""


class XBRLMetadataError(XBRLToolError, RuntimeError):
    """Authoritative filing, context, or fact metadata is inconsistent."""


class XBRLNumericError(XBRLMetadataError):
    """A fact marked numeric by ingestion cannot be parsed losslessly."""


class XBRLDuplicateFactIDError(XBRLMetadataError):
    """Two ingested rows have the same stable local fact identity."""


@dataclass(frozen=True)
class XBRLDimension:
    """One authoritative explicit or typed context dimension."""

    axis: str
    member: str

    def to_dict(self) -> dict[str, str]:
        return {"axis": self.axis, "member": self.member}


@dataclass(frozen=True)
class ConceptSearchResult:
    """One locally observed exact concept identity."""

    rank: int
    concept: str
    namespace_prefix: str | None
    local_name: str
    fact_count: int
    unit_refs_observed: tuple[str, ...]
    unit_measures_observed: tuple[tuple[str, ...], ...]
    unit_numerators_observed: tuple[tuple[str, ...], ...]
    unit_denominators_observed: tuple[tuple[str, ...], ...]
    companies_observed: tuple[str, ...]
    accessions_observed: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "concept": self.concept,
            "namespace_prefix": self.namespace_prefix,
            "local_name": self.local_name,
            "fact_count": self.fact_count,
            "unit_refs_observed": list(self.unit_refs_observed),
            "unit_measures_observed": [
                list(measures) for measures in self.unit_measures_observed
            ],
            "unit_numerators_observed": [
                list(measures) for measures in self.unit_numerators_observed
            ],
            "unit_denominators_observed": [
                list(measures) for measures in self.unit_denominators_observed
            ],
            "companies_observed": list(self.companies_observed),
            "accessions_observed": list(self.accessions_observed),
        }


@dataclass(frozen=True)
class XBRLFact:
    """One authoritative local fact plus its filing and context metadata."""

    stable_fact_id: str
    fact_id: str
    doc_id: str
    concept: str
    namespace_prefix: str | None
    local_name: str
    raw_value: str
    normalized_value: str | None
    unit: str
    unit_measures: tuple[str, ...]
    unit_numerator: tuple[str, ...]
    unit_denominator: tuple[str, ...]
    decimals: str
    scale: int
    sign: str | None
    is_negative: bool
    context_ref: str
    period_type: str
    instant: str | None
    period_start: str | None
    period_end: str | None
    duration_days: int | None
    dimensions: tuple[XBRLDimension, ...] | None
    accession: str
    company: str
    cik: str
    entity_identifier: str
    entity_scheme: str
    form_type: str
    filing_date: str
    period_of_report: str
    filing_fiscal_period: str
    calendar_period: str
    source_role: str
    doc_role: str
    chunk_id: str | None
    fact_locator: str

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.__dict__)
        payload["unit_measures"] = list(self.unit_measures)
        payload["unit_numerator"] = list(self.unit_numerator)
        payload["unit_denominator"] = list(self.unit_denominator)
        payload["dimensions"] = (
            None
            if self.dimensions is None
            else [dimension.to_dict() for dimension in self.dimensions]
        )
        return payload


@dataclass(frozen=True)
class XBRLTrace:
    """Deterministic, timestamp-free audit trace for one XBRL call."""

    tool_name: str
    tool_version: str
    operation: str
    inputs: Mapping[str, Any]
    xbrl_artifact_version: str
    xbrl_artifact_fingerprint: str
    ingestion_schema_version: str
    corpus_fingerprint: str
    matched_count: int
    returned_count: int
    returned_concept_ids: tuple[str, ...]
    returned_fact_ids: tuple[str, ...]
    concepts: tuple[str, ...]
    accessions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "operation": self.operation,
            "inputs": copy.deepcopy(dict(self.inputs)),
            "xbrl_artifact_version": self.xbrl_artifact_version,
            "xbrl_artifact_fingerprint": self.xbrl_artifact_fingerprint,
            "ingestion_schema_version": self.ingestion_schema_version,
            "corpus_fingerprint": self.corpus_fingerprint,
            "matched_count": self.matched_count,
            "returned_count": self.returned_count,
            "returned_concept_ids": list(self.returned_concept_ids),
            "returned_fact_ids": list(self.returned_fact_ids),
            "concepts": list(self.concepts),
            "accessions": list(self.accessions),
        }

    def canonical_json(self) -> str:
        return canonical_xbrl_trace_json(self)


@dataclass(frozen=True)
class ConceptSearchResponse:
    """Public response for deterministic local concept discovery."""

    tool_version: str
    query: str
    top_k: int
    matched_count: int
    results: tuple[ConceptSearchResult, ...]
    trace: XBRLTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "query": self.query,
            "top_k": self.top_k,
            "matched_count": self.matched_count,
            "results": [result.to_dict() for result in self.results],
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class FactQueryResponse:
    """Public response containing every fact matching exact filters."""

    tool_version: str
    filters: Mapping[str, Any]
    matched_count: int
    facts: tuple[XBRLFact, ...]
    trace: XBRLTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "filters": copy.deepcopy(dict(self.filters)),
            "matched_count": self.matched_count,
            "facts": [fact.to_dict() for fact in self.facts],
            "trace": self.trace.to_dict(),
        }


def canonical_xbrl_trace_json(trace: XBRLTrace | Mapping[str, Any]) -> str:
    """Return canonical UTF-8 JSON text suitable for content hashing."""
    payload = trace.to_dict() if isinstance(trace, XBRLTrace) else dict(trace)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


class XBRLTool:
    """Reusable deterministic interface over frozen local inline-XBRL facts."""

    def __init__(
        self,
        *,
        fact_records: Sequence[Mapping[str, Any]],
        xbrl_artifact_fingerprint: str,
        ingestion_schema_version: str,
        corpus_fingerprint: str,
    ) -> None:
        if not xbrl_artifact_fingerprint:
            raise XBRLArtifactError("xbrl_artifact_fingerprint must be non-empty")
        if not ingestion_schema_version:
            raise XBRLArtifactError("ingestion_schema_version must be non-empty")
        if not corpus_fingerprint:
            raise XBRLArtifactError("corpus_fingerprint must be non-empty")

        self._xbrl_artifact_fingerprint = xbrl_artifact_fingerprint
        self._ingestion_schema_version = ingestion_schema_version
        self._corpus_fingerprint = corpus_fingerprint
        self._facts_by_id: dict[str, XBRLFact] = {}
        by_concept: defaultdict[str, list[XBRLFact]] = defaultdict(list)
        accession_identities: dict[str, tuple[str, str, str]] = {}

        for record in fact_records:
            fact = self._public_fact(record)
            if self._normalized_cik(fact.entity_identifier) != self._normalized_cik(
                fact.cik
            ):
                raise XBRLMetadataError(
                    f"entity/manifest CIK mismatch for {fact.stable_fact_id}: "
                    f"{fact.entity_identifier!r} != {fact.cik!r}"
                )
            identity = (fact.company, fact.cik, fact.entity_identifier)
            previous_identity = accession_identities.setdefault(
                fact.accession, identity
            )
            if previous_identity != identity:
                raise XBRLMetadataError(
                    f"inconsistent accession/entity metadata for {fact.accession}"
                )
            if fact.stable_fact_id in self._facts_by_id:
                raise XBRLDuplicateFactIDError(
                    f"duplicate stable fact ID: {fact.stable_fact_id}"
                )
            self._facts_by_id[fact.stable_fact_id] = fact
            by_concept[fact.concept].append(fact)

        if not self._facts_by_id:
            raise XBRLArtifactError("local XBRL ingestion contains no facts")

        self._facts = tuple(
            self._facts_by_id[key] for key in sorted(self._facts_by_id)
        )
        self._facts_by_concept = {
            concept: tuple(sorted(facts, key=lambda fact: fact.stable_fact_id))
            for concept, facts in sorted(by_concept.items())
        }
        self._concepts = tuple(self._facts_by_concept)

    @classmethod
    def from_frozen_ingestion(
        cls, *, data_dir: str | Path = _DEFAULT_DATA_DIR
    ) -> "XBRLTool":
        """Load and index immutable local artifacts once for repeated calls."""
        data_path = Path(data_dir)
        manifest_path = data_path / "manifest.json"
        if not manifest_path.is_file():
            raise XBRLArtifactError(f"missing local XBRL manifest: {manifest_path}")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise XBRLArtifactError(
                f"failed to read local XBRL manifest: {manifest_path}"
            ) from exc

        schema_version = str(manifest.get("ingestion_schema_version", ""))
        corpus_fingerprint = str(manifest.get("corpus_fingerprint", ""))
        if schema_version != EXPECTED_INGESTION_SCHEMA_VERSION:
            raise XBRLArtifactError(
                "ingestion schema mismatch: "
                f"expected={EXPECTED_INGESTION_SCHEMA_VERSION} actual={schema_version}"
            )
        if corpus_fingerprint != EXPECTED_CORPUS_FINGERPRINT:
            raise XBRLArtifactError(
                "corpus fingerprint mismatch: "
                f"expected={EXPECTED_CORPUS_FINGERPRINT} actual={corpus_fingerprint}"
            )

        entries = manifest.get("entries")
        if not isinstance(entries, list) or not entries:
            raise XBRLArtifactError("local XBRL manifest contains no entries")

        try:
            links = cls._load_chunk_links(data_path, entries)
            records, identity_documents = cls._load_fact_records(
                data_path, entries, links
            )
        except XBRLToolError:
            raise
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise XBRLArtifactError(
                f"failed to load frozen local XBRL artifacts: {exc}"
            ) from exc

        linked_identities = set(links)
        loaded_identities = {
            (str(record["doc_id"]), str(record["fact_id"])) for record in records
        }
        unknown_links = linked_identities - loaded_identities
        if unknown_links:
            first = sorted(unknown_links)[0]
            raise XBRLMetadataError(
                f"chunk links unknown XBRL fact: {first[0]}::{first[1]}"
            )

        identity = {
            "xbrl_artifact_version": XBRL_ARTIFACT_VERSION,
            "ingestion_schema_version": schema_version,
            "corpus_fingerprint": corpus_fingerprint,
            "documents": identity_documents,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            fact_records=records,
            xbrl_artifact_fingerprint=fingerprint,
            ingestion_schema_version=schema_version,
            corpus_fingerprint=corpus_fingerprint,
        )

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    @property
    def concept_count(self) -> int:
        return len(self._concepts)

    @property
    def xbrl_artifact_fingerprint(self) -> str:
        return self._xbrl_artifact_fingerprint

    def search_concepts(
        self, query: str, top_k: int = 10
    ) -> ConceptSearchResponse:
        """Discover locally observed concepts using deterministic lexical matching."""
        normalized_query = self._validate_search_call(query, top_k)
        scored: list[tuple[tuple[Any, ...], str]] = []
        for concept in self._concepts:
            score = self._concept_score(normalized_query, concept)
            if score is not None:
                scored.append((score, concept))
        scored.sort(key=lambda item: item[0])
        matched_count = len(scored)
        returned_concepts = tuple(concept for _, concept in scored[:top_k])
        results = tuple(
            self._concept_result(rank, concept)
            for rank, concept in enumerate(returned_concepts, start=1)
        )
        accessions = tuple(
            sorted(
                {
                    fact.accession
                    for concept in returned_concepts
                    for fact in self._facts_by_concept[concept]
                }
            )
        )
        trace = self._trace(
            operation="search_concepts",
            inputs={"query": normalized_query, "top_k": top_k},
            matched_count=matched_count,
            returned_concept_ids=returned_concepts,
            concepts=returned_concepts,
            accessions=accessions,
        )
        return ConceptSearchResponse(
            tool_version=TOOL_VERSION,
            query=normalized_query,
            top_k=top_k,
            matched_count=matched_count,
            results=results,
            trace=trace,
        )

    def query_facts(
        self,
        *,
        concept: str,
        accession: str | None = None,
        company: str | None = None,
        form_type: str | None = None,
        filing_fiscal_period: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        instant: str | None = None,
        unit: str | None = None,
        include_dimensions: bool = True,
    ) -> FactQueryResponse:
        """Return all rows matching one exact concept and exact structured filters."""
        filters = self._validate_fact_filters(
            concept=concept,
            accession=accession,
            company=company,
            form_type=form_type,
            filing_fiscal_period=filing_fiscal_period,
            period_start=period_start,
            period_end=period_end,
            instant=instant,
            unit=unit,
            include_dimensions=include_dimensions,
        )
        if filters["concept"] not in self._facts_by_concept:
            raise XBRLInputError(f"unknown exact concept: {filters['concept']}")

        facts = self._facts_by_concept[str(filters["concept"])]
        selected = tuple(
            fact
            for fact in facts
            if self._matches_filters(fact, filters)
        )
        if not include_dimensions:
            selected = tuple(replace(fact, dimensions=None) for fact in selected)

        fact_ids = tuple(fact.stable_fact_id for fact in selected)
        accessions = tuple(sorted({fact.accession for fact in selected}))
        trace = self._trace(
            operation="query_facts",
            inputs=filters,
            matched_count=len(selected),
            returned_fact_ids=fact_ids,
            concepts=(str(filters["concept"]),),
            accessions=accessions,
        )
        return FactQueryResponse(
            tool_version=TOOL_VERSION,
            filters=filters,
            matched_count=len(selected),
            facts=selected,
            trace=trace,
        )

    def _trace(
        self,
        *,
        operation: str,
        inputs: Mapping[str, Any],
        matched_count: int,
        returned_concept_ids: tuple[str, ...] = (),
        returned_fact_ids: tuple[str, ...] = (),
        concepts: tuple[str, ...] = (),
        accessions: tuple[str, ...] = (),
    ) -> XBRLTrace:
        return XBRLTrace(
            tool_name=TOOL_NAME,
            tool_version=TOOL_VERSION,
            operation=operation,
            inputs=copy.deepcopy(dict(inputs)),
            xbrl_artifact_version=XBRL_ARTIFACT_VERSION,
            xbrl_artifact_fingerprint=self._xbrl_artifact_fingerprint,
            ingestion_schema_version=self._ingestion_schema_version,
            corpus_fingerprint=self._corpus_fingerprint,
            matched_count=matched_count,
            returned_count=(
                len(returned_fact_ids)
                if operation == "query_facts"
                else len(returned_concept_ids)
            ),
            returned_concept_ids=returned_concept_ids,
            returned_fact_ids=returned_fact_ids,
            concepts=concepts,
            accessions=accessions,
        )

    @classmethod
    def _load_chunk_links(
        cls, data_path: Path, entries: Sequence[Mapping[str, Any]]
    ) -> dict[tuple[str, str], str]:
        links: dict[tuple[str, str], str] = {}
        for entry in cls._ordered_entries(entries):
            doc_id = cls._required_text(entry, "doc_id")
            path = data_path / "chunks" / f"{doc_id}.json"
            cls._verify_file(path, str(entry.get("chunk_sha256", "")), "chunk")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("doc_id") != doc_id:
                raise XBRLMetadataError(f"chunk document mismatch for {doc_id}")
            if payload.get("accession") != entry.get("accession"):
                raise XBRLMetadataError(f"chunk accession mismatch for {doc_id}")
            for chunk in payload.get("chunks", []):
                chunk_id = cls._required_text(chunk, "chunk_id")
                for fact in chunk.get("xbrl_facts", []):
                    key = (
                        cls._required_text(fact, "doc_id"),
                        cls._required_text(fact, "fact_id"),
                    )
                    if fact.get("accession") != entry.get("accession"):
                        raise XBRLMetadataError(
                            f"chunk fact accession mismatch for {key[0]}::{key[1]}"
                        )
                    previous = links.get(key)
                    if previous is not None and previous != chunk_id:
                        raise XBRLMetadataError(
                            f"XBRL fact links multiple chunks: {key[0]}::{key[1]}"
                        )
                    links[key] = chunk_id
        return links

    @classmethod
    def _load_fact_records(
        cls,
        data_path: Path,
        entries: Sequence[Mapping[str, Any]],
        links: Mapping[tuple[str, str], str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        identity_documents: list[dict[str, Any]] = []
        seen_docs: set[str] = set()
        for entry in cls._ordered_entries(entries):
            doc_id = cls._required_text(entry, "doc_id")
            if doc_id in seen_docs:
                raise XBRLMetadataError(f"duplicate manifest doc_id: {doc_id}")
            seen_docs.add(doc_id)
            accession = cls._required_text(entry, "accession")
            if not _ACCESSION_RE.fullmatch(accession):
                raise XBRLMetadataError(
                    f"malformed manifest accession for {doc_id}: {accession}"
                )

            raw_path = Path(cls._required_text(entry, "local_path"))
            raw_hash = str(entry.get("raw_sha256") or entry.get("sha256") or "")
            cls._verify_file(raw_path, raw_hash, "raw")
            parsed_path = data_path / "parsed" / f"{doc_id}.json"
            cls._verify_file(
                parsed_path, str(entry.get("parsed_sha256", "")), "parsed"
            )
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            if parsed.get("doc_id") != doc_id:
                raise XBRLMetadataError(f"parsed document mismatch for {doc_id}")
            if parsed.get("accession") != accession:
                raise XBRLMetadataError(f"parsed accession mismatch for {doc_id}")

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                soup = BeautifulSoup(raw_path.read_bytes(), "lxml")
            xbrl = parse_inline_xbrl(
                soup,
                doc_id=doc_id,
                accession=accession,
                source_role=cls._required_text(entry, "source_role"),
            )
            declared_count = parsed.get("xbrl_fact_count")
            if isinstance(declared_count, bool) or not isinstance(declared_count, int):
                raise XBRLMetadataError(
                    f"invalid parsed XBRL fact count for {doc_id}: {declared_count!r}"
                )
            if len(xbrl["facts"]) != declared_count:
                raise XBRLMetadataError(
                    f"XBRL fact count mismatch for {doc_id}: "
                    f"declared={declared_count} parsed={len(xbrl['facts'])}"
                )

            contexts: dict[str, Mapping[str, Any]] = {}
            for context in xbrl["contexts"]:
                context_id = cls._required_text(context, "id")
                if context_id in contexts:
                    raise XBRLMetadataError(
                        f"duplicate context ID for {doc_id}: {context_id}"
                    )
                contexts[context_id] = context

            units: dict[str, Mapping[str, Any]] = {}
            for unit in xbrl["units"]:
                unit_id = cls._required_text(unit, "id")
                if unit_id in units:
                    raise XBRLMetadataError(
                        f"duplicate unit ID for {doc_id}: {unit_id}"
                    )
                units[unit_id] = unit

            for fact in xbrl["facts"]:
                context_id = cls._required_text(fact, "context_id")
                context = contexts.get(context_id)
                if context is None:
                    raise XBRLMetadataError(
                        f"fact references unknown context: {doc_id}::{fact.get('fact_id')}"
                    )
                if fact.get("accession") != accession:
                    raise XBRLMetadataError(
                        f"fact accession mismatch for {doc_id}::{fact.get('fact_id')}"
                    )
                unit_ref = str(fact.get("unit", ""))
                unit = units.get(unit_ref) if unit_ref else None
                if unit_ref and unit is None:
                    raise XBRLMetadataError(
                        f"fact references unknown unit: {doc_id}::{fact.get('fact_id')}"
                    )
                entity_identifier = str(context.get("entity_identifier", ""))
                cik = cls._required_text(entry, "cik")
                if cls._normalized_cik(entity_identifier) != cls._normalized_cik(cik):
                    raise XBRLMetadataError(
                        f"entity/manifest CIK mismatch for {doc_id}: "
                        f"{entity_identifier!r} != {cik!r}"
                    )
                enriched = copy.deepcopy(dict(fact))
                enriched.update(
                    {
                        "company": cls._required_text(entry, "company"),
                        "cik": cik,
                        "entity_identifier": entity_identifier,
                        "entity_scheme": str(context.get("scheme", "")),
                        "form_type": cls._required_text(entry, "form"),
                        "filing_date": cls._required_text(entry, "filing_date"),
                        "period_of_report": str(entry.get("period_of_report", "")),
                        "fiscal_period": cls._required_text(entry, "fiscal_period"),
                        "calendar_period": str(entry.get("calendar_period", "")),
                        "doc_role": str(entry.get("doc_role", "")),
                        "chunk_id": links.get((doc_id, str(fact.get("fact_id", "")))),
                        "unit_numerator": [] if unit is None else unit.get("numerator", []),
                        "unit_denominator": []
                        if unit is None
                        else unit.get("denominator", []),
                    }
                )
                records.append(enriched)

            identity_documents.append(
                {
                    "doc_id": doc_id,
                    "accession": accession,
                    "raw_sha256": raw_hash,
                    "xbrl_fact_count": len(xbrl["facts"]),
                }
            )
        return records, identity_documents

    @staticmethod
    def _ordered_entries(
        entries: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        if not all(isinstance(entry, Mapping) for entry in entries):
            raise XBRLArtifactError("manifest entries must be objects")
        return sorted(entries, key=lambda entry: str(entry.get("doc_id", "")))

    @staticmethod
    def _verify_file(path: Path, expected_hash: str, label: str) -> None:
        if not path.is_file():
            raise XBRLArtifactError(f"missing local XBRL {label} artifact: {path}")
        if not expected_hash:
            raise XBRLArtifactError(f"missing {label} hash for artifact: {path}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise XBRLArtifactError(
                f"{label} artifact hash mismatch for {path}: "
                f"expected={expected_hash} actual={actual_hash}"
            )

    @staticmethod
    def _required_text(record: Mapping[str, Any], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise XBRLMetadataError(f"required metadata field is empty: {field}")
        return value

    @staticmethod
    def _normalized_cik(value: str) -> str:
        if not value.isdigit():
            raise XBRLMetadataError(f"CIK must contain only digits: {value!r}")
        return value.lstrip("0") or "0"

    @classmethod
    def _public_fact(cls, record: Mapping[str, Any]) -> XBRLFact:
        doc_id = cls._required_text(record, "doc_id")
        fact_id = cls._required_text(record, "fact_id")
        accession = cls._required_text(record, "accession")
        if not _ACCESSION_RE.fullmatch(accession):
            raise XBRLMetadataError(
                f"malformed fact accession for {doc_id}::{fact_id}: {accession}"
            )
        concept = cls._required_text(record, "concept")
        prefix, local_name = cls._split_concept(concept)
        context_ref = cls._required_text(record, "context_id")
        instant = cls._optional_source_date(record.get("instant_date"), "instant_date")
        start = cls._optional_source_date(record.get("period_start"), "period_start")
        end = cls._optional_source_date(record.get("period_end"), "period_end")
        if instant and (start or end):
            raise XBRLMetadataError(
                f"fact has instant and duration dates: {doc_id}::{fact_id}"
            )
        if bool(start) != bool(end):
            raise XBRLMetadataError(
                f"fact has incomplete duration dates: {doc_id}::{fact_id}"
            )
        if instant:
            period_type = "instant"
            duration_days = None
        elif start and end:
            if date.fromisoformat(end) < date.fromisoformat(start):
                raise XBRLMetadataError(
                    f"fact duration ends before it starts: {doc_id}::{fact_id}"
                )
            period_type = "duration"
            duration_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        else:
            raise XBRLMetadataError(
                f"fact has no authoritative period: {doc_id}::{fact_id}"
            )

        dimensions_value = record.get("dimensions", [])
        if not isinstance(dimensions_value, list):
            raise XBRLMetadataError(
                f"dimensions must be a list for {doc_id}::{fact_id}"
            )
        dimensions: list[XBRLDimension] = []
        for dimension in dimensions_value:
            if not isinstance(dimension, Mapping):
                raise XBRLMetadataError(
                    f"dimension must be an object for {doc_id}::{fact_id}"
                )
            dimensions.append(
                XBRLDimension(
                    axis=str(dimension.get("axis", "")),
                    member=str(dimension.get("member", "")),
                )
            )

        scale = record.get("scale", 0)
        if isinstance(scale, bool) or not isinstance(scale, int):
            raise XBRLNumericError(
                f"invalid numeric scale for {doc_id}::{fact_id}: {scale!r}"
            )
        raw_value = str(record.get("raw_visible_text", ""))
        normalized_value = None
        if record.get("parsed_value") is not None:
            normalized_value = cls._normalized_numeric_value(
                raw_value=raw_value,
                sign=record.get("sign"),
                scale=scale,
                stable_fact_id=f"{doc_id}::{fact_id}",
            )

        measures_value = record.get("unit_measures", [])
        if not isinstance(measures_value, list):
            raise XBRLMetadataError(
                f"unit_measures must be a list for {doc_id}::{fact_id}"
            )
        numerator_value = record.get("unit_numerator", [])
        denominator_value = record.get("unit_denominator", [])
        if not isinstance(numerator_value, list) or not isinstance(
            denominator_value, list
        ):
            raise XBRLMetadataError(
                f"divide-unit measures must be lists for {doc_id}::{fact_id}"
            )
        is_negative = record.get("is_negative", False)
        if not isinstance(is_negative, bool):
            raise XBRLMetadataError(
                f"is_negative must be boolean for {doc_id}::{fact_id}"
            )
        chunk_id_value = record.get("chunk_id")
        chunk_id = None if chunk_id_value is None else str(chunk_id_value)
        return XBRLFact(
            stable_fact_id=f"{doc_id}::{fact_id}",
            fact_id=fact_id,
            doc_id=doc_id,
            concept=concept,
            namespace_prefix=prefix,
            local_name=local_name,
            raw_value=raw_value,
            normalized_value=normalized_value,
            unit=str(record.get("unit", "")),
            unit_measures=tuple(str(item) for item in measures_value),
            unit_numerator=tuple(str(item) for item in numerator_value),
            unit_denominator=tuple(str(item) for item in denominator_value),
            decimals=str(record.get("decimals", "")),
            scale=scale,
            sign=(None if record.get("sign") is None else str(record.get("sign"))),
            is_negative=is_negative,
            context_ref=context_ref,
            period_type=period_type,
            instant=instant,
            period_start=start,
            period_end=end,
            duration_days=duration_days,
            dimensions=tuple(dimensions),
            accession=accession,
            company=cls._required_text(record, "company"),
            cik=cls._required_text(record, "cik"),
            entity_identifier=cls._required_text(record, "entity_identifier"),
            entity_scheme=str(record.get("entity_scheme", "")),
            form_type=cls._required_text(record, "form_type"),
            filing_date=cls._required_text(record, "filing_date"),
            period_of_report=str(record.get("period_of_report", "")),
            filing_fiscal_period=cls._required_text(record, "fiscal_period"),
            calendar_period=str(record.get("calendar_period", "")),
            source_role=cls._required_text(record, "source_role"),
            doc_role=str(record.get("doc_role", "")),
            chunk_id=chunk_id,
            fact_locator=f"{doc_id}#{fact_id}",
        )

    @staticmethod
    def _normalized_numeric_value(
        *, raw_value: str, sign: Any, scale: int, stable_fact_id: str
    ) -> str:
        cleaned = raw_value.replace("\u00a0", " ").strip()
        is_negative = sign == "-" or (
            cleaned.startswith("(") and cleaned.endswith(")")
        )
        cleaned = cleaned.replace(",", "").replace(" ", "").strip("()")
        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:]
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if not _NUMBER_RE.fullmatch(cleaned):
            raise XBRLNumericError(
                f"malformed numeric value for {stable_fact_id}: {raw_value!r}"
            )
        try:
            value = Decimal(cleaned)
            if is_negative:
                value = -value
            value *= Decimal(10) ** scale
        except (InvalidOperation, OverflowError) as exc:
            raise XBRLNumericError(
                f"malformed numeric value for {stable_fact_id}: {raw_value!r}"
            ) from exc
        return XBRLTool._canonical_decimal(value)

    @staticmethod
    def _canonical_decimal(value: Decimal) -> str:
        if value == 0:
            return "0"
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered

    @staticmethod
    def _optional_source_date(value: Any, field: str) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise XBRLMetadataError(f"{field} must be an ISO date string")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise XBRLMetadataError(f"malformed source {field}: {value!r}") from exc
        if parsed.isoformat() != value:
            raise XBRLMetadataError(f"non-canonical source {field}: {value!r}")
        return value

    @staticmethod
    def _split_concept(concept: str) -> tuple[str | None, str]:
        if ":" not in concept:
            return None, concept
        prefix, local_name = concept.split(":", 1)
        return prefix or None, local_name

    @staticmethod
    def _validate_search_call(query: str, top_k: int) -> str:
        if not isinstance(query, str) or not query.strip():
            raise XBRLInputError("query must be a non-empty string")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise XBRLInputError("top_k must be an integer")
        if top_k < 1 or top_k > MAX_TOP_K:
            raise XBRLInputError("top_k must be between 1 and 50 inclusive")
        return query.strip()

    @classmethod
    def _concept_score(
        cls, query: str, concept: str
    ) -> tuple[Any, ...] | None:
        _, local_name = cls._split_concept(concept)
        query_folded = query.casefold()
        concept_folded = concept.casefold()
        local_folded = local_name.casefold()
        query_compact = cls._compact_lexical(query)
        concept_compact = cls._compact_lexical(concept)
        local_compact = cls._compact_lexical(local_name)
        query_tokens = set(cls._lexical_tokens(query))
        concept_tokens = set(cls._lexical_tokens(concept))
        overlap = len(query_tokens & concept_tokens)

        if query_folded == concept_folded:
            tier = 0
        elif query_folded == local_folded:
            tier = 1
        elif query_compact and query_compact in local_compact:
            tier = 2
        elif query_compact and query_compact in concept_compact:
            tier = 3
        elif overlap:
            tier = 4
        else:
            return None
        return (
            tier,
            -overlap,
            abs(len(local_compact) - len(query_compact)),
            concept,
        )

    @staticmethod
    def _compact_lexical(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    @staticmethod
    def _lexical_tokens(value: str) -> tuple[str, ...]:
        return tuple(match.group(0).casefold() for match in _WORD_RE.finditer(value))

    def _concept_result(self, rank: int, concept: str) -> ConceptSearchResult:
        facts = self._facts_by_concept[concept]
        prefix, local_name = self._split_concept(concept)
        return ConceptSearchResult(
            rank=rank,
            concept=concept,
            namespace_prefix=prefix,
            local_name=local_name,
            fact_count=len(facts),
            unit_refs_observed=tuple(sorted({fact.unit for fact in facts if fact.unit})),
            unit_measures_observed=tuple(
                sorted({fact.unit_measures for fact in facts if fact.unit_measures})
            ),
            unit_numerators_observed=tuple(
                sorted({fact.unit_numerator for fact in facts if fact.unit_numerator})
            ),
            unit_denominators_observed=tuple(
                sorted(
                    {fact.unit_denominator for fact in facts if fact.unit_denominator}
                )
            ),
            companies_observed=tuple(sorted({fact.company for fact in facts})),
            accessions_observed=tuple(sorted({fact.accession for fact in facts})),
        )

    @classmethod
    def _validate_fact_filters(cls, **filters: Any) -> dict[str, Any]:
        concept = filters["concept"]
        if not isinstance(concept, str) or not concept:
            raise XBRLInputError("concept must be a non-empty exact concept string")
        accession = filters["accession"]
        if accession is not None:
            if not isinstance(accession, str) or not _ACCESSION_RE.fullmatch(accession):
                raise XBRLInputError(
                    "accession must match the SEC form ##########-##-######"
                )
        for field in ("company", "form_type", "filing_fiscal_period"):
            value = filters[field]
            if value is not None and (not isinstance(value, str) or not value):
                raise XBRLInputError(f"{field} must be a non-empty string or None")
        unit = filters["unit"]
        if unit is not None and not isinstance(unit, str):
            raise XBRLInputError("unit must be an exact string or None")
        include_dimensions = filters["include_dimensions"]
        if not isinstance(include_dimensions, bool):
            raise XBRLInputError("include_dimensions must be a boolean")
        for field in ("period_start", "period_end", "instant"):
            value = filters[field]
            if value is not None:
                filters[field] = cls._validate_filter_date(value, field)
        if filters["instant"] is not None and (
            filters["period_start"] is not None or filters["period_end"] is not None
        ):
            raise XBRLInputError(
                "instant cannot be combined with period_start or period_end"
            )
        return dict(filters)

    @staticmethod
    def _validate_filter_date(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise XBRLInputError(f"{field} must be an ISO date string")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise XBRLInputError(f"malformed {field}: {value!r}") from exc
        if parsed.isoformat() != value:
            raise XBRLInputError(f"malformed {field}: {value!r}")
        return value

    @staticmethod
    def _matches_filters(fact: XBRLFact, filters: Mapping[str, Any]) -> bool:
        fields = (
            ("accession", fact.accession),
            ("company", fact.company),
            ("form_type", fact.form_type),
            ("filing_fiscal_period", fact.filing_fiscal_period),
            ("period_start", fact.period_start),
            ("period_end", fact.period_end),
            ("instant", fact.instant),
            ("unit", fact.unit),
        )
        return all(filters[field] is None or filters[field] == value for field, value in fields)
