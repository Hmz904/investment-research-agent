"""Deterministic resolution of provisioned frozen data artifacts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


FROZEN_RAW_SUFFIXES = frozenset({".htm"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FrozenDataError(RuntimeError):
    """Base class for provisioned frozen-data failures."""


class FrozenDataPathError(FrozenDataError):
    """Manifest path metadata cannot map to the frozen data root."""


class FrozenDataMissingError(FrozenDataError):
    """A required provisioned frozen artifact is absent."""


class FrozenDataHashError(FrozenDataError):
    """A provisioned artifact does not match its frozen digest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_explicit_root(root: str | Path, *, label: str) -> Path:
    candidate = Path(root)
    if not candidate.is_absolute():
        raise FrozenDataPathError(f"{label} must be an explicit absolute path: {root}")
    try:
        return candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FrozenDataMissingError(f"missing {label}: {candidate}") from exc


def resolve_raw_document(
    *, data_root: str | Path, manifest_entry: Mapping[str, Any]
) -> Path:
    """Resolve one hash-verified raw document strictly beneath ``data_root``.

    ``local_path`` is retained only as historical basename/suffix metadata. Its
    directory is never inspected or used as a candidate runtime location.
    """
    root = normalize_explicit_root(data_root, label="frozen data root")
    doc_id = manifest_entry.get("doc_id")
    historical = manifest_entry.get("local_path")
    if not isinstance(doc_id, str) or not doc_id:
        raise FrozenDataPathError("manifest entry has no non-empty doc_id")
    if not isinstance(historical, str) or not historical:
        raise FrozenDataPathError(f"manifest entry has no historical local_path: {doc_id}")

    basename = Path(historical).name
    suffix = Path(basename).suffix.lower()
    if suffix not in FROZEN_RAW_SUFFIXES:
        raise FrozenDataPathError(
            f"unsupported frozen raw suffix for {doc_id}: {suffix or '<none>'}"
        )
    expected_basename = f"{doc_id}{suffix}"
    if basename != expected_basename:
        raise FrozenDataPathError(
            f"historical raw basename mismatch for {doc_id}: "
            f"expected={expected_basename!r} actual={basename!r}"
        )

    candidate = (root / "raw" / basename).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise FrozenDataPathError(f"frozen raw path escapes data root: {candidate}")
    if not candidate.is_file():
        raise FrozenDataMissingError(
            f"missing provisioned frozen raw document for {doc_id}: {candidate}"
        )

    expected_hash = manifest_entry.get("raw_sha256") or manifest_entry.get("sha256")
    if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(expected_hash):
        raise FrozenDataHashError(f"invalid frozen raw SHA-256 metadata for {doc_id}")
    actual_hash = sha256_file(candidate)
    if actual_hash != expected_hash:
        raise FrozenDataHashError(
            f"frozen raw SHA-256 mismatch for {doc_id}: "
            f"expected={expected_hash} actual={actual_hash}"
        )
    return candidate
