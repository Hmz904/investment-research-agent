"""One-command SEC filing ingestion pipeline."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .chunking import chunk_blocks
from .corpus import SOURCES
from .parser import extract_blocks
from .sec import SECClient
from .storage import RawStore
from .xbrl import parse_inline_xbrl


warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _prepare_dirs() -> None:
    for sub in ("raw", "parsed", "chunks"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)


def _content_type_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix == ".xml":
        return "application/xml"
    return "application/octet-stream"


def run() -> dict[str, Any]:
    _prepare_dirs()
    client = SECClient()
    store = RawStore(DATA_DIR)

    manifest_entries: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "documents": 0,
        "blocks": 0,
        "tables": 0,
        "chunks": 0,
        "xbrl_facts": 0,
        "numeric_table_cells_with_header_periods": 0,
        "downloaded_raw_files": 0,
        "reused_raw_files": 0,
    }

    for source in SOURCES:
        doc_id = source["doc_id"]
        entry = store.try_reuse(source)
        downloaded = False
        if entry is None:
            metadata, document_url, document_name = client.discover(source)
            entry, downloaded = store.ensure(
                source=source,
                metadata=metadata,
                document_url=document_url,
                document_name=document_name,
                fetch=client.fetch_document,
            )
        manifest_entries.append(entry)
        if downloaded:
            summary["downloaded_raw_files"] += 1
        else:
            summary["reused_raw_files"] += 1

        raw_path = Path(entry["local_path"])
        body = raw_path.read_bytes()
        if not entry.get("content_type"):
            entry["content_type"] = _content_type_from_path(raw_path)

        soup = BeautifulSoup(body, "lxml")
        xbrl = parse_inline_xbrl(
            soup,
            doc_id=doc_id,
            accession=source["accession"],
            source_role=source["source_role"],
        )
        blocks = extract_blocks(
            soup,
            doc_id=doc_id,
            accession=source["accession"],
            source_role=source["source_role"],
            fact_by_id=xbrl["fact_by_id"],
            contexts=xbrl["contexts"],
            root_section=(
                f"Exhibit {source['exhibit_number']}"
                if source.get("doc_role") == "exhibit" and source.get("exhibit_number")
                else None
            ),
        )
        chunks = chunk_blocks(
            doc_id=doc_id,
            accession=source["accession"],
            source_role=source["source_role"],
            blocks=blocks,
        )

        parsed_path = DATA_DIR / "parsed" / f"{doc_id}.json"
        chunks_path = DATA_DIR / "chunks" / f"{doc_id}.json"
        parsed_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "accession": source["accession"],
                    "source_role": source["source_role"],
                    "xbrl_fact_count": len(xbrl["facts"]),
                    "blocks": blocks,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        chunks_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "accession": source["accession"],
                    "source_role": source["source_role"],
                    "chunks": chunks,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        summary["documents"] += 1
        summary["blocks"] += len(blocks)
        summary["tables"] += sum(1 for b in blocks if b["block_type"] == "table")
        summary["chunks"] += len(chunks)
        summary["xbrl_facts"] += len(xbrl["facts"])
        summary["numeric_table_cells_with_header_periods"] += _count_header_period_cells(blocks)

    store.save_manifest(manifest_entries)
    return summary


def _count_header_period_cells(blocks: list[dict[str, Any]]) -> int:
    count = 0
    for block in blocks:
        if block["block_type"] != "table":
            continue
        for row in block.get("table", {}).get("rows", []):
            for cell in row.get("cells", []):
                if cell.get("period_source") == "header" and cell.get("parsed_value") is not None:
                    count += 1
    return count


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nIngestion summary")
    for key in (
        "documents",
        "blocks",
        "tables",
        "chunks",
        "xbrl_facts",
        "numeric_table_cells_with_header_periods",
        "downloaded_raw_files",
        "reused_raw_files",
    ):
        print(f"  {key}: {summary[key]}")


def main(argv: list[str] | None = None) -> int:
    summary = run()
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
