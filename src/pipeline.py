"""One-command SEC filing ingestion pipeline."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any, Literal

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .chunking import chunk_blocks
from .corpus import SOURCES
from .parser import extract_blocks
from .sec import SECClient
from .storage import RawStore, sha256_hex
from .xbrl import parse_inline_xbrl


warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _prepare_dirs(data_dir: Path) -> None:
    for sub in ("raw", "parsed", "chunks"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)


def _content_type_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix == ".xml":
        return "application/xml"
    return "application/octet-stream"


def run(
    *,
    data_root: Path | str | None = None,
    data_dir: Path | str | None = None,
    mode: Literal["discovery", "frozen"] = "discovery",
) -> dict[str, Any]:
    if data_root is not None and data_dir is not None:
        raise ValueError("provide data_root or data_dir, not both")
    selected_root = data_root if data_root is not None else data_dir
    if mode == "frozen" and selected_root is None:
        raise ValueError("frozen pipeline mode requires an explicit data_root")
    active_data_dir = DATA_DIR if selected_root is None else Path(selected_root)
    if mode == "frozen" and not active_data_dir.is_absolute():
        raise ValueError("frozen pipeline data_root must be absolute")
    if mode == "discovery":
        _prepare_dirs(active_data_dir)
    elif not active_data_dir.is_dir():
        raise FileNotFoundError(f"missing frozen data root: {active_data_dir}")
    client: SECClient | None = None
    store = RawStore(active_data_dir, mode=mode)

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
            if mode == "frozen":
                raise RuntimeError(f"missing provisioned frozen input for {doc_id}")
            client = SECClient()
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

        expected_parsed_hash = str(entry.get("parsed_sha256", ""))
        expected_chunk_hash = str(entry.get("chunk_sha256", ""))
        raw_path = store.resolve_entry(entry)
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

        parsed_path = active_data_dir / "parsed" / f"{doc_id}.json"
        chunks_path = active_data_dir / "chunks" / f"{doc_id}.json"
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

        entry["raw_sha256"] = sha256_hex(body)
        entry["parsed_sha256"] = sha256_hex(parsed_path.read_bytes())
        entry["chunk_sha256"] = sha256_hex(chunks_path.read_bytes())
        if mode == "frozen":
            if entry["parsed_sha256"] != expected_parsed_hash:
                raise RuntimeError(
                    f"rebuilt parsed artifact drift for {doc_id}: "
                    f"expected={expected_parsed_hash} actual={entry['parsed_sha256']}"
                )
            if entry["chunk_sha256"] != expected_chunk_hash:
                raise RuntimeError(
                    f"rebuilt chunk artifact drift for {doc_id}: "
                    f"expected={expected_chunk_hash} actual={entry['chunk_sha256']}"
                )

        summary["documents"] += 1
        summary["blocks"] += len(blocks)
        summary["tables"] += sum(1 for b in blocks if b["block_type"] == "table")
        summary["chunks"] += len(chunks)
        summary["xbrl_facts"] += len(xbrl["facts"])
        summary["numeric_table_cells_with_header_periods"] += _count_header_period_cells(blocks)

    if mode == "frozen":
        from .storage import corpus_fingerprint

        summary["corpus_fingerprint"] = corpus_fingerprint(manifest_entries)
    else:
        summary["corpus_fingerprint"] = store.save_manifest(manifest_entries)
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
        "corpus_fingerprint",
    ):
        print(f"  {key}: {summary[key]}")


def main(argv: list[str] | None = None) -> int:
    summary = run()
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
