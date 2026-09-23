"""Immutable raw-byte storage and ingestion manifest handling."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


INGESTION_SCHEMA_VERSION = "0.1.1"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def corpus_fingerprint(
    entries: list[dict[str, Any]],
    ingestion_schema_version: str = INGESTION_SCHEMA_VERSION,
) -> str:
    """Hash only deterministic corpus identity fields."""
    identity = {
        "ingestion_schema_version": ingestion_schema_version,
        "raw_artifact_hashes": sorted(entry["raw_sha256"] for entry in entries),
        "parsed_artifact_hashes": sorted(entry["parsed_sha256"] for entry in entries),
        "chunk_artifact_hashes": sorted(entry["chunk_sha256"] for entry in entries),
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_hex(canonical)


class RawStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.raw_dir = data_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = data_dir / "manifest.json"

    def load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"entries": []}
        with self.manifest_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _by_doc_id(self, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {entry["doc_id"]: entry for entry in manifest.get("entries", [])}

    def try_reuse(self, source: dict[str, Any]) -> dict[str, Any] | None:
        """Return a valid existing manifest entry without touching the network."""
        doc_id = source["doc_id"]
        manifest = self.load_manifest()
        entry = self._by_doc_id(manifest).get(doc_id)
        if entry is None:
            return None
        raw_path = Path(entry.get("local_path", ""))
        if not raw_path.exists():
            return None
        stored_hash = entry.get("sha256", "")
        actual_hash = sha256_hex(raw_path.read_bytes())
        if stored_hash and actual_hash != stored_hash:
            raise RuntimeError(
                f"raw file hash mismatch for {doc_id}: "
                f"manifest={stored_hash} actual={actual_hash}"
            )
        return dict(entry)

    def ensure(
        self,
        source: dict[str, Any],
        metadata: dict[str, str],
        document_url: str,
        document_name: str,
        fetch: Any,
    ) -> tuple[dict[str, Any], bool]:
        """Download or reuse one immutable raw document.

        Returns ``(manifest_entry, downloaded)`` where ``downloaded`` is True
        only when bytes were newly fetched from SEC.
        """
        doc_id = source["doc_id"]
        manifest = self.load_manifest()
        entries = self._by_doc_id(manifest)
        existing = entries.get(doc_id)

        ext = Path(document_name).suffix or ".htm"
        raw_path = self.raw_dir / f"{doc_id}{ext}"

        if existing is not None and raw_path.exists():
            stored_hash = existing.get("sha256", "")
            actual_hash = sha256_hex(raw_path.read_bytes())
            if stored_hash and actual_hash != stored_hash:
                raise RuntimeError(
                    f"raw file hash mismatch for {doc_id}: "
                    f"manifest={stored_hash} actual={actual_hash}"
                )
            return dict(existing), False

        if existing is None and raw_path.exists():
            # Reuse an existing immutable file from an earlier partial run.
            actual_hash = sha256_hex(raw_path.read_bytes())
            entry = self._build_entry(
                source=source,
                metadata=metadata,
                document_url=document_url,
                content_type="",
                sha256=actual_hash,
                size=raw_path.stat().st_size,
                retrieved_at=existing["retrieved_at"] if existing else _utc_now_iso(),
            )
            return entry, False

        fetched = fetch(document_url)
        body = fetched.body
        content_type = fetched.content_type
        actual_hash = sha256_hex(body)

        # A prior run with the same doc_id but a missing file means the bytes
        # changed; do not silently replace it.
        if existing is not None:
            raise RuntimeError(
                f"raw file for {doc_id} is missing but manifest already records "
                f"sha256={existing.get('sha256')}"
            )

        self._atomic_write(raw_path, body)
        entry = self._build_entry(
            source=source,
            metadata=metadata,
            document_url=document_url,
            content_type=content_type,
            sha256=actual_hash,
            size=len(body),
            retrieved_at=_utc_now_iso(),
        )
        return entry, True

    def _build_entry(
        self,
        source: dict[str, Any],
        metadata: dict[str, str],
        document_url: str,
        content_type: str,
        sha256: str,
        size: int,
        retrieved_at: str,
    ) -> dict[str, Any]:
        doc_id = source["doc_id"]
        ext = Path(metadata.get("document_name", "")).suffix or ".htm"
        return {
            "doc_id": doc_id,
            "cik": source["cik"],
            "company": source["company"],
            "form": source["form"],
            "accession": source["accession"],
            "filing_date": metadata.get("filing_date", ""),
            "period_of_report": metadata.get("period_of_report", ""),
            "fiscal_period": source["fiscal_period"],
            "calendar_period": source["calendar_period"],
            "source_role": source["source_role"],
            "doc_role": source["doc_role"],
            "exhibit_number": source.get("exhibit_number", ""),
            "source_url": document_url,
            "content_type": content_type,
            "sha256": sha256,
            "bytes": size,
            "retrieved_at": retrieved_at,
            "local_path": str(self.raw_dir / f"{doc_id}{ext}"),
        }

    def _atomic_write(self, path: Path, data: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def save_manifest(self, entries: list[dict[str, Any]]) -> str:
        fingerprint = corpus_fingerprint(entries)
        payload = {
            "generated_at": _utc_now_iso(),
            "ingestion_schema_version": INGESTION_SCHEMA_VERSION,
            "corpus_fingerprint": fingerprint,
            "entries": entries,
        }
        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        os.replace(tmp_path, self.manifest_path)
        return fingerprint
