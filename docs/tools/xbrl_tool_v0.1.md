# XBRLTool v0.1

## Contract

`XBRLTool` returns reported facts from the frozen local inline-XBRL filings. It
does not contact SEC, EDGAR, a taxonomy service, or any other network service.
It does not calculate, infer, restate, reconcile, rank, or select an
economically preferred fact.

```python
from src.tools import XBRLTool

tool = XBRLTool.from_frozen_ingestion()
concepts = tool.search_concepts("assets", top_k=10)
facts = tool.query_facts(
    concept="us-gaap:Assets",
    accession="0000000000-00-000000",
    instant="2026-03-31",
)
```

The accession above only illustrates the required format. A valid exact query
can return zero rows. An unobserved exact concept is an error rather than a
request to broaden or reinterpret the concept.

## Authoritative local artifacts

The fact source is the immutable inline-XBRL in `data/raw`, interpreted by the
existing `src.xbrl.parse_inline_xbrl` ingestion parser. `data/manifest.json`
provides document metadata, hashes, ingestion schema version, and the frozen
corpus fingerprint. The per-document declared `xbrl_fact_count` values in
`data/parsed` are checked against newly parsed local rows. `data/chunks` is used
only to propagate an existing exact fact-to-chunk linkage.

The production corpus has 7,839 authoritative fact rows and 746 exact concepts
under ingestion schema `0.1.1`. The parsed block and chunk views link 7,199 of
those facts because hidden or otherwise non-rendered inline facts are not
embedded in visible blocks. XBRLTool therefore parses the frozen raw bytes once
at construction instead of treating the smaller block view as the complete
fact table. It does not modify or regenerate any ingestion artifact.

`from_frozen_ingestion()` verifies:

- the expected ingestion schema and frozen corpus fingerprint;
- raw, parsed, and chunk file hashes from the manifest;
- document and accession consistency across artifacts;
- each parsed artifact's declared fact count;
- context existence, entity CIK consistency, and unique context IDs;
- unique stable fact identities and valid fact periods; and
- that every propagated chunk link names a loaded fact.

The XBRL-specific fingerprint in every trace is SHA-256 over a canonical
identity payload containing the XBRL artifact version, ingestion schema,
corpus fingerprint, and ordered document accession/raw-hash/fact-count tuples.

## Actual source fields

The ingested fact rows contain:

- `doc_id`, `accession`, `source_role`, `fact_id`, `concept`, and `context_id`;
- `period_start`, `period_end`, and `instant_date`;
- ordered `dimensions` (`axis`, `member`) and the redundant `members` list;
- raw unit reference, direct `unit_measures`, and divide-unit numerator and
  denominator measures;
- `decimals`, `scale`, `sign`, and `is_negative`;
- `raw_visible_text`, `parsed_value`, and `scaled_value`.

The context table additionally contains the entity identifier and scheme. The
manifest supplies company, CIK, form, filing date, period of report, fiscal
period, calendar period, source role, and document role. A fact embedded in a
chunk has one exact `chunk_id`; 640 facts have no chunk linkage.

The frozen ingestion does **not** store taxonomy namespace URIs, authoritative
labels, XBRL `precision`, SEC `frame`, a separate fiscal-year field, or
statement/presentation metadata. XBRLTool does not synthesize them. It exposes
the QName prefix as `namespace_prefix`, not as a namespace URI. Consequently,
v0.1 has no `fiscal_year` filter; `fiscal_period` is the exact manifest value.
The public name for that filing-level value is `filing_fiscal_period`.

## Public API

```python
tool.search_concepts(query: str, top_k: int = 10) -> ConceptSearchResponse

tool.query_facts(
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
) -> FactQueryResponse
```

`search_concepts()` searches only observed QNames and local names. Its lexical
tiers are case-folded exact QName, exact local name, compact local-name
substring, compact QName substring, and token overlap. Within a tier it orders
by token overlap, length distance, and ascending exact concept. There are no
labels in the ingestion, no synonyms, embeddings, taxonomy lookup, or manual
financial terminology. Results provide exact concept identity, QName prefix
and local name, fact count, observed raw unit references, direct and
divide-unit measures, companies, and accessions.

`query_facts()` requires a case-sensitive exact concept identity. Every other
supplied filter is also an exact equality filter. `unit` means the ingested raw
unit reference (for example, two documents may use different references for
the same observed measure). The response contains all matches ordered by
ascending stable fact identity; it has no limit, preferred-context logic, or
fallback. `include_dimensions=False` removes only the returned dimension
payload and never changes which rows match.

## Fact response

Each result exposes:

- stable identity `doc_id::fact_id`, original `fact_id`, and `doc_id`;
- exact concept, QName prefix, and local name;
- original `raw_value` and lossless string `normalized_value` when numeric;
- raw unit reference, direct/divide unit measures, decimals, scale, sign, and
  the ingestion's negative flag;
- context reference, period type, dates, duration days, and dimensions;
- accession, company, CIK, entity identifier/scheme, form, and filing date;
- period of report, filing fiscal/calendar periods, source/document roles;
- optional authoritative `chunk_id`; and
- deterministic `fact_locator`, constructed as `doc_id#fact_id`.

`stable_fact_id` (`doc_id::fact_id`) is the globally unique local identity used
in traces. `fact_locator` is a deterministic XBRL fact reference constructed
by XBRLTool from two ingested identity fields. The combined string is not an
ingested source-text locator, document URL, or narrative citation. Bare
`fact_id` values are document-local and can collide across filings. A
`chunk_id` is exposed only when the frozen chunk artifact directly links that
fact. It is authoritative narrative/chunk linkage and is never fabricated for
an unlinked fact.

## Numeric policy

`raw_value` preserves the ingested visible lexical value. Frozen ingestion
removes display separators and applies the inline-XBRL `sign` when constructing
`parsed_value`; it does not apply `scale` to `parsed_value`. Ingestion's
`scaled_value` then multiplies that signed value by `10 ** scale` using its
historical float representation. `decimals` and unit fields remain metadata.

If ingestion marked a fact as parsed numeric, XBRLTool independently reparses
the original lexical text with `Decimal`, applies `sign` once, applies the
ingested scale exponent once, and serializes the result as a canonical,
non-exponent decimal string such as `"48554"`, `"0.07"`, or `"-0.28"`. Thus
`normalized_value` has the exact numeric meaning of ingestion's
`scaled_value` without inheriting binary-float approximation. A nil, dash, or
nonnumeric ingested fact has `normalized_value=None` and is not forced through
Decimal parsing. An invalid lexical value that ingestion claims is numeric
raises `XBRLNumericError`.

## Period and dimension semantics

An instant fact has `period_type="instant"` and an `instant` date. A duration
fact has `period_type="duration"`, exact start/end dates, and
`duration_days`, defined exactly as
`(end_date - start_date).days + 1`: the inclusive number of calendar dates in
that reported interval. It is descriptive context only; v0.1 has no hidden
quarter, YTD, or annual classifier. Filing metadata is returned unchanged and
is not used to rewrite or classify fact context dates.

In particular, `filing_fiscal_period="FY26Q2"` describes the filing and does
not establish that a fact duration is quarter-only. The same filing may contain
three-month, YTD, comparative, and instant facts. A three-month duration and a
year-to-date duration ending on the same date remain separate rows. XBRLTool
never computes one from the other.

Dimensions retain their ingested order and axis/member values. Facts sharing a
concept, period, and unit remain separate when their contexts differ. Even
byte-equivalent economic rows remain separate if they have distinct ingested
fact IDs. V0.1 never prefers dimensionless, consolidated, largest, or latest
values and never silently deduplicates.

## Point-in-time boundary

Every row remains bound to its frozen `doc_id` and accession. The accession
filter is exact and accepts only the SEC `##########-##-######` shape. No value
from another or later filing is substituted because its concept or period
matches. XBRLTool does not access Company Facts or live/restated SEC data.
Its production imports and runtime path contain no HTTP client, SEC client,
external taxonomy API, or network concept lookup.

## Deterministic trace

Both operations return an `XBRLTrace` containing:

- tool name/version and operation;
- the exact query or complete filter object;
- XBRL artifact version/fingerprint, ingestion schema, and corpus fingerprint;
- matched and returned counts;
- ordered returned concept IDs or stable fact IDs; and
- returned concepts and accessions.

`canonical_xbrl_trace_json()` uses sorted keys, compact separators,
UTF-8-compatible JSON, finite numbers only, and one terminal newline. Traces
contain no timestamps.

Fact traces always use global `doc_id::fact_id` identities, never bare
document-local fact IDs.

## Provenance boundary

Narrative evidence provenance may use an authoritative `chunk_id`, accession,
and narrative locator. Structured numeric calculation provenance may use
`stable_fact_id` or `fact_locator`, accession, exact concept, `context_ref`,
period dates, unit metadata, and the optional authoritative `chunk_id` where a
link exists. An unlinked XBRL fact must not masquerade as a narrative citation.

The frozen `agent_output_schema_v0.1` is not changed by this tool. If future
agent integration needs a dedicated structured-XBRL provenance object, that is
a future schema/version change rather than part of XBRLTool v0.1.

## Errors and lifecycle

Explicit error classes distinguish bad input, missing/invalid artifacts,
metadata inconsistency, malformed numeric data, and duplicate stable fact IDs.
Input validation covers empty discovery queries, `top_k` outside 1–50,
unknown exact concepts, malformed accessions and ISO dates, and incompatible
instant/duration filters. Known concepts with no matching filtered rows return
an empty response normally and never broaden the query.

Each tool instance reads and validates local artifacts, parses facts, and
builds fact/concept indices exactly once. Repeated searches and queries reuse
the in-memory immutable fact objects and lookup maps. There is no mutable
global singleton.

## Responsibility boundary

XBRLTool returns reported XBRL facts. It does **not** decide:

- which accounting fact is economically appropriate;
- whether a duration is quarter-only or year-to-date beyond exposing dates;
- which dimensional context should be preferred;
- whether two facts should be subtracted; or
- whether GAAP and non-GAAP values are interchangeable.

Those decisions belong to auditable agent reasoning and, for arithmetic, a
separate CalculatorTool. XBRLTool v0.1 performs no derived arithmetic.
