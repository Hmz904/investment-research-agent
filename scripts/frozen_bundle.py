"""Shared validation helpers for frozen project-data bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


class BundleError(RuntimeError):
    """A bundle or provisioned tree violates its frozen contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BundleError(f"expected JSON object: {path}")
    return payload


def validate_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise BundleError(f"unsafe bundle path: {value!r}")
    if "\\" in value:
        raise BundleError(f"non-POSIX bundle path: {value!r}")
    return path


def data_entries(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise BundleError("bundle manifest files must be a list")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise BundleError("bundle file entries must be objects")
        path = str(row.get("path", ""))
        validate_relative_path(path)
        if path in seen:
            raise BundleError(f"duplicate bundle path: {path}")
        folded = path.casefold()
        if folded in seen_casefold:
            raise BundleError(f"case-colliding bundle path: {path}")
        seen.add(path)
        seen_casefold.add(folded)
        output.append(dict(row))
    output.sort(key=lambda item: str(item["path"]))
    if manifest.get("file_count") != len(output):
        raise BundleError("bundle file_count does not match entries")
    if manifest.get("total_bytes") != sum(int(item["bytes"]) for item in output):
        raise BundleError("bundle total_bytes does not match entries")
    aggregate_lines = "".join(
        f"{item['sha256']}  {item['path']}\n" for item in output
    ).encode("utf-8")
    aggregate = hashlib.sha256(aggregate_lines).hexdigest()
    if manifest.get("aggregate_sha256") != aggregate:
        raise BundleError("bundle aggregate_sha256 does not match entries")
    return output


def verify_files(
    root: Path,
    entries: Sequence[Mapping[str, Any]],
    *,
    reject_unexpected: bool,
) -> None:
    expected = {str(item["path"]) for item in entries}
    top_level = {PurePosixPath(path).parts[0] for path in expected}
    for item in entries:
        relative = str(item["path"])
        path = root.joinpath(*PurePosixPath(relative).parts)
        if path.is_symlink() or not path.is_file():
            raise BundleError(f"missing or non-regular frozen file: {relative}")
        size = path.stat().st_size
        if size != int(item["bytes"]):
            raise BundleError(
                f"frozen file size mismatch for {relative}: "
                f"expected={item['bytes']} actual={size}"
            )
        digest = sha256_file(path)
        if digest != item["sha256"]:
            raise BundleError(
                f"frozen file SHA-256 mismatch for {relative}: "
                f"expected={item['sha256']} actual={digest}"
            )
    if reject_unexpected:
        actual: set[str] = set()
        for name in sorted(top_level):
            start = root / name
            if start.is_symlink():
                raise BundleError(f"link in managed frozen tree: {name}")
            if start.is_file():
                actual.add(name)
            elif start.exists():
                for path in start.rglob("*"):
                    if path.is_symlink():
                        raise BundleError(
                            f"link in managed frozen tree: {path.relative_to(root)}"
                        )
                    if path.is_file():
                        actual.add(path.relative_to(root).as_posix())
        unexpected = sorted(actual - expected)
        if unexpected:
            raise BundleError(f"unexpected files in managed frozen tree: {unexpected}")
