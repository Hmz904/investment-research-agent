# Week 1 Step 1 — SEC Filing Ingestion

Work in the current repository.

Implement ONLY the SEC filing ingestion layer described below.

## Scope isolation

Do not modify anything under `benchmark/`.

Production ingestion code must not read, import, inspect, copy, index, or derive
implementation logic from:

- benchmark/frozen/questions.csv
- benchmark/frozen/numeric_answers.csv
- benchmark/frozen/evidence_checklist.csv
- benchmark/frozen/protocol.md

The explicit source list below is sufficient.

Do NOT implement:

- BM25
- embeddings
- vector databases
- reranking
- query rewriting
- LLM calls
- agent logic
- benchmark scoring
- benchmark provenance tests

Ask before installing any package outside:

- requests
- lxml
- beautifulsoup4
- pandas
- pytest

Stop when ingestion and its general parser tests pass.

---

# 1. Source corpus

Ingest exactly these 14 SEC documents.

## NVIDIA — CIK 1045810

Historical references:

- FY26 Q2 10-Q
  - accession: `0001045810-25-000209`
  - source_role: `historical_reference`

- FY26 Q4 earnings 8-K Exhibit 99.1
  - accession: `0001045810-26-000019`
  - ingest Exhibit 99.1 only
  - source_role: `historical_reference`

Benchmark periods:

- FY27 Q1 10-Q
  - accession: `0001045810-26-000052`
  - source_role: `benchmark_period`

- FY27 Q1 earnings 8-K Exhibit 99.1
  - accession: `0001045810-26-000051`
  - ingest Exhibit 99.1 only
  - source_role: `benchmark_period`

- FY27 Q2 10-Q
  - accession: `0001045810-26-000075`
  - source_role: `benchmark_period`

- FY27 Q2 earnings 8-K Exhibit 99.1
  - accession: `0001045810-26-000073`
  - ingest Exhibit 99.1 only
  - source_role: `benchmark_period`

## Microsoft — CIK 789019

- FY26 Q3 10-Q
  - accession: `0001193125-26-191507`
  - source_role: `benchmark_period`

- FY26 Q3 earnings 8-K Exhibit 99.1
  - accession: `0001193125-26-191457`
  - ingest Exhibit 99.1 only
  - source_role: `benchmark_period`

- FY26 10-K
  - accession: `0001193125-26-323660`
  - source_role: `benchmark_period`

- FY26 Q4 earnings 8-K Exhibit 99.1
  - accession: `0001193125-26-323632`
  - ingest Exhibit 99.1 only
  - source_role: `benchmark_period`

## Meta — CIK 1326801

- 2026 Q1 10-Q
  - accession: `0001628280-26-028526`
  - source_role: `benchmark_period`

- 2026 Q1 earnings 8-K Exhibit 99.1
  - accession: `0001628280-26-028364`
  - ingest Exhibit 99.1 only
  - source_role: `benchmark_period`

- 2026 Q2 10-Q
  - accession: `0001628280-26-050705`
  - source_role: `benchmark_period`

- 2026 Q2 earnings 8-K Exhibit 99.1
  - accession: `0001628280-26-050596`
  - ingest Exhibit 99.1 only
  - source_role: `benchmark_period`

The generated ingestion manifest must contain all 14 accessions and preserve
`source_role`.

---

# 2. SEC access

Use SEC EDGAR filing index pages to discover the actual filing documents.

Use environment variable:

`SEC_USER_AGENT`

as the HTTP User-Agent.

Requirements:

- remain comfortably below 10 requests/second
- deterministic throttling
- conservative retry for transient failures
- do not hammer SEC endpoints
- do not hard-code final SEC document URLs when they can be discovered from
  the filing index

For 8-K sources, ingest only Exhibit 99.1.

---

# 3. Immutable raw storage

Store immutable downloaded bytes under:

`data/raw/`

Maintain an ingestion manifest containing at least:

- doc_id
- cik
- company
- form
- accession
- filing_date
- period_of_report
- fiscal_period
- calendar_period
- source_role
- doc_role
- exhibit_number
- source_url
- content_type
- sha256
- bytes
- retrieved_at

Rules:

1. Never silently overwrite an existing raw document with different bytes.
2. If a raw file exists, verify its SHA-256 before reuse.
3. If stored bytes and expected manifest hash disagree, fail explicitly.
4. A second pipeline run should reuse valid raw files rather than blindly
   redownload them.
5. Remote content differing from previously stored immutable content must
   produce an explicit error.

---

# 4. Parsing

Parse SEC HTML / inline-XBRL documents into ordered blocks.

Support at least:

- heading
- paragraph
- table
- footnote

Preserve source order.

Each block should retain:

- doc_id
- accession
- source_role
- document position
- section_path
- block_type
- raw or normalized text

Build useful section paths where possible, such as:

- Part I > Item 1
- Part I > Item 2
- Part II > Item 1A
- Risk Factors
- Management's Discussion and Analysis
- Note N

Do not implement accession-specific or company-specific parser fixes.

---

# 5. Structured tables

Tables are first-class structured objects.

Preserve where available:

- caption/title
- headers
- multi-row headers
- row labels
- column labels
- individual cells
- raw cell text
- parsed numeric value
- unit scale
- footnotes
- document order

Never split one logical table row across chunks.

When chunking a large table:

- repeat required headers
- group complete rows
- preserve table identity
- preserve period provenance
- preserve attached footnotes

Parse accounting parentheses correctly where appropriate.

Example:

`(4,028)` -> `-4028`

Do not treat ordinary textual parentheses as negative-number notation.

---

# 6. Fact-level and cell-level period provenance

This is a critical requirement.

Period metadata must be attached to individual XBRL facts or numeric table
cells.

Chunk-level period metadata is only a summary and is not authoritative.

## Inline-XBRL facts

For each usable tagged fact preserve, when available:

- concept
- context_id
- period_start
- period_end
- instant_date
- dimensions
- members
- unit
- decimals
- scale
- sign
- raw_visible_text
- parsed_value

A duration fact must retain both start and end.

For example:

- 2026-01-01 -> 2026-03-31
- 2025-07-01 -> 2026-03-31

must remain distinct even when they share the same concept and row label.

## Untagged table cells

For every numeric table cell whose period is inferable from table headers,
retain at least:

- raw_text
- parsed_value
- row_label
- column_label
- period_start
- period_end
- period_label
- period_source = "header"
- unit_scale

Period inference must be generic and header-driven.

Do not write rules tied to:

- accession
- company
- expected benchmark number

---

# 7. Chunking

Write chunks under:

`data/chunks/`

Chunk IDs must be stable and reproducible from immutable document identity
plus document position.

Each chunk should contain at least:

- chunk_id
- doc_id
- accession
- source_role
- section_path
- block_type
- text
- table_json when applicable
- period_columns or period summary
- unit_scale when applicable
- xbrl_facts when applicable
- char_start
- char_end
- prev_chunk_id
- next_chunk_id
- token_count or deterministic approximate token count

Text rules:

- do not cross major section boundaries
- preserve paragraph boundaries
- target roughly 400-800 tokens
- use at most one-paragraph overlap

Table rules:

- never split an individual row
- repeat necessary headers
- retain structured cells
- retain period provenance
- retain attached footnotes

---

# 8. Repository layout

Use a simple layout such as:

data/
  raw/
  parsed/
  chunks/
  manifest.*

src/
  ...

tests/
  ...

Do not introduce unnecessary frameworks or abstraction layers.

Use Python.

Use English for code, comments, filenames, and implementation documentation.

---

# 9. One-command pipeline

Provide one clear command for the complete ingestion process.

Prefer:

`python -m src.pipeline`

or an equivalently simple command.

It must:

1. resolve the 14 SEC sources
2. download or validate immutable raw files
3. parse the documents
4. extract structured tables
5. extract inline-XBRL metadata
6. derive generic table-header period provenance
7. generate chunks
8. write the ingestion manifest
9. print a concise summary

Summary must include:

- documents
- blocks
- tables
- chunks
- XBRL facts
- numeric table cells with header-derived periods
- downloaded raw files
- reused raw files

---

# 10. Acceptance tests

Acceptance values may be hard-coded in TESTS.

Production parsing code must not contain test-specific logic.

## A. NVIDIA FY27 Q1 10-Q

Recover a table/chunk containing:

- Data Center 75,246
- comparable/recast Data Center 39,112

and retain nearby recast/presentation context.

Current and comparable periods must remain distinguishable.

## B. NVIDIA FY27 Q2 10-Q

Recover:

- Hyperscale 48,710
- recast FY27 Q1 Hyperscale 43,050

and retain nearby context explaining the ACIE -> Hyperscale reclassification.

Period and provenance must remain attached.

## C. Microsoft FY26 Q3 10-Q

Cash-flow parsing must recover:

- Additions to property and equipment = 30,876
- Additions to property and equipment = 80,146

The tagged facts must retain concept:

`PaymentsToAcquirePropertyPlantAndEquipment`

and distinguish:

- 2026-01-01 -> 2026-03-31
- 2025-07-01 -> 2026-03-31

Do not collapse these into one fact because their labels match.

## D. Microsoft FY26 Q4 Exhibit 99.1

Recover Intelligent Cloud:

- revenue 39,306
- gross profit 16,876
- operating income 15,955

The cells must retain header-derived period provenance and correctly identify
the three-month period.

## E. Microsoft FY26 10-K

A Risk Factors chunk must contain:

`underutilization of infrastructure`

with a sensible Risk Factors section path.

## F. Meta 2026 Q2 Exhibit 99.1

Free-cash-flow reconciliation must recover:

- 784
- 8,549

and distinguish the correct three-month columns with header-derived periods.

## G. Corpus integrity

All 14 accessions must appear in the generated ingestion manifest.

The manifest must identify exactly:

- 12 `benchmark_period`
- 2 `historical_reference`

A second full pipeline run must:

- succeed
- reuse valid raw files where possible
- verify matching SHA-256 hashes
- never silently overwrite raw sources

---

# 11. Extra spot checks

Report these after the main tests.

## Meta 2026 Q1 Exhibit 99.1

Find the segment table containing approximately:

- Family of Apps operating income: 26,900
- Reality Labs operating loss: (4,028)

Verify:

- parentheses are preserved
- parsed Reality Labs value is negative

## NVIDIA FY27 Q2 10-Q

Find the accounts-receivable concentration paragraph containing approximately:

- 22%
- 14%
- 13%
- 11%
- 10%

Return:

- complete paragraph
- section_path
- accession

## Microsoft FY26 10-K

Return one representative long-form Intelligent Cloud MD&A chunk demonstrating:

- good paragraph-boundary chunking
- useful section_path
- no accidental cross-section contamination

---

# 12. Anti-overfitting requirements

Never implement production logic like:

- if accession == "..."
- if company == "NVIDIA": ...
- if value == 75246: ...
- company-specific table offsets
- expected-answer-specific cleanup

Acceptance checks are probes of general ingestion behavior.

When a check fails, fix the generic parser rule.

---

# 13. Benchmark isolation

Production ingestion code must not read frozen answer/checklist files.

Do not use benchmark answers to:

- repair tables
- choose chunks
- identify expected values
- infer periods
- rank content
- select parser behavior

A future benchmark-side provenance test may compare frozen evidence with the
chunk store. That test is OUT OF SCOPE now.

---

# 14. Final report

Work autonomously until all ingestion acceptance tests pass.

Then STOP.

Do not proceed to retrieval or agent implementation.

Report:

1. `git status`
2. `git diff --stat`
3. repository tree for implementation files
4. complete pytest output
5. pipeline summary
6. all acceptance-test results
7. paths to raw / parsed / chunks / ingestion manifest
8. representative structured output for:
   - Microsoft 30,876 vs 80,146 with fact-level periods
   - Microsoft Q4 Intelligent Cloud table cells with header-derived periods
   - Meta 784 vs 8,549 with header-derived periods
   - NVIDIA Q2 recast/reclassification
   - Microsoft Risk Factors
9. all three extra spot checks

Do not merely state that tests pass. Show the relevant structured output.

Do not modify benchmark files.

Do not implement anything beyond this task.
