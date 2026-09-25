"""Provision and verify the frozen project data and logical model payloads."""

from __future__ import annotations

import argparse
import os
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.frozen_bundle import (
        BundleError,
        data_entries,
        load_json_object,
        sha256_file,
        validate_relative_path,
        verify_files,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` invocation.
    from frozen_bundle import (
        BundleError,
        data_entries,
        load_json_object,
        sha256_file,
        validate_relative_path,
        verify_files,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_MANIFEST = PROJECT_ROOT / "packaging" / "frozen_runtime_bundle_v0.1.json"
MODEL_MANIFEST = PROJECT_ROOT / "packaging" / "frozen_model_payloads_v0.1.json"
RELEASE_MANIFEST = (
    PROJECT_ROOT / "packaging" / "frozen_runtime_bundle_release_v0.1.json"
)


def _require_absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise BundleError(f"{label} must be an explicit absolute path: {path}")
    return path.resolve(strict=False)


def _model_entries(payload: dict[str, Any]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    models = payload.get("models")
    if not isinstance(models, list) or len(models) != 2:
        raise BundleError("model manifest must declare exactly two models")
    output: list[tuple[str, str, list[dict[str, Any]]]] = []
    total_files = 0
    total_bytes = 0
    for model in models:
        if not isinstance(model, dict):
            raise BundleError("model declarations must be objects")
        model_id = str(model.get("model_id", ""))
        revision = str(model.get("revision", ""))
        files = model.get("files")
        if not model_id or not revision or not isinstance(files, list):
            raise BundleError("malformed model declaration")
        rows: list[dict[str, Any]] = []
        for item in files:
            if not isinstance(item, dict):
                raise BundleError("model file declarations must be objects")
            validate_relative_path(str(item.get("path", "")))
            rows.append(dict(item))
            total_bytes += int(item["bytes"])
        total_files += len(rows)
        output.append((model_id, revision, rows))
    if total_files != payload.get("file_count") or total_files != 12:
        raise BundleError("model manifest file_count mismatch")
    if total_bytes != payload.get("total_bytes"):
        raise BundleError("model manifest total_bytes mismatch")
    return output


def _verify_models(model_root: Path, payload: dict[str, Any]) -> None:
    canonical: list[dict[str, Any]] = []
    for model_id, revision, entries in _model_entries(payload):
        prefix = f"{model_id.replace('/', '--')}/{revision}"
        canonical.extend(
            {**entry, "path": f"{prefix}/{entry['path']}"} for entry in entries
        )
    verify_files(model_root, canonical, reject_unexpected=True)
    expected = {str(entry["path"]) for entry in canonical}
    actual: set[str] = set()
    for path in model_root.rglob("*"):
        if path.is_symlink():
            raise BundleError(
                f"link in frozen model tree: {path.relative_to(model_root)}"
            )
        if path.is_file():
            actual.add(path.relative_to(model_root).as_posix())
    unexpected = sorted(actual - expected)
    if unexpected:
        raise BundleError(f"unexpected files in frozen model tree: {unexpected}")


def _archive_source(bundle: str, offline_dir: Path | None, temporary: Path) -> Path:
    release = load_json_object(RELEASE_MANIFEST)
    asset_name = str(release["asset_name"])
    expected_hash = str(release["archive_sha256"])
    expected_size = int(release["archive_bytes"])
    parsed = urllib.parse.urlparse(bundle)
    if offline_dir is not None:
        source = offline_dir / asset_name
    elif parsed.scheme in {"http", "https"}:
        if "/latest/" in parsed.path or Path(parsed.path).name != asset_name:
            raise BundleError("remote bundle must name the immutable registered asset")
        release_tag = str(release["future_release_tag"])
        if f"/download/{release_tag}/" not in parsed.path:
            raise BundleError("remote bundle URL does not contain the registered release tag")
        source = temporary / asset_name
        with urllib.request.urlopen(bundle) as response, source.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    elif parsed.scheme:
        raise BundleError(f"unsupported bundle URL scheme: {parsed.scheme}")
    else:
        source = Path(bundle)
    if not source.is_file():
        raise BundleError(f"frozen data archive not found: {source}")
    if source.stat().st_size != expected_size:
        raise BundleError("frozen data archive size mismatch")
    if sha256_file(source) != expected_hash:
        raise BundleError("frozen data archive SHA-256 mismatch")
    return source


def _extract_archive(archive_path: Path, stage: Path, entries: list[dict[str, Any]]) -> None:
    expected_by_path = {str(item["path"]): item for item in entries}
    expected = set(expected_by_path)
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    with tarfile.open(archive_path, mode="r:*") as archive:
        for member in archive:
            relative = member.name
            validate_relative_path(relative)
            if relative in seen:
                raise BundleError(f"duplicate archive member: {relative}")
            folded = relative.casefold()
            if folded in seen_casefold:
                raise BundleError(f"case-colliding archive member: {relative}")
            seen.add(relative)
            seen_casefold.add(folded)
            if not member.isfile() or member.issym() or member.islnk():
                raise BundleError(f"archive member is not a regular file: {relative}")
            if relative not in expected:
                raise BundleError(f"unexpected archive member: {relative}")
            if member.size != int(expected_by_path[relative]["bytes"]):
                raise BundleError(f"archive member size mismatch: {relative}")
            destination = stage.joinpath(*validate_relative_path(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise BundleError(f"cannot read archive member: {relative}")
            with source, destination.open("xb") as handle:
                shutil.copyfileobj(source, handle)
    missing = sorted(expected - seen)
    if missing:
        raise BundleError(f"missing archive members: {missing}")
    verify_files(stage, entries, reject_unexpected=True)


def _stage_models(
    stage: Path,
    payload: dict[str, Any],
    offline_dir: Path | None,
    download_cache: Path,
) -> None:
    for model_id, revision, entries in _model_entries(payload):
        destination = stage / model_id.replace("/", "--") / revision
        destination.mkdir(parents=True, exist_ok=True)
        for item in entries:
            filename = str(item["path"])
            if offline_dir is not None:
                source = (
                    offline_dir
                    / "models"
                    / model_id.replace("/", "--")
                    / revision
                    / filename
                )
            else:
                from huggingface_hub import hf_hub_download

                source = Path(
                    hf_hub_download(
                        repo_id=model_id,
                        filename=filename,
                        revision=revision,
                        local_files_only=False,
                        cache_dir=str(download_cache),
                    )
                )
            if not source.is_file():
                raise BundleError(f"model payload file not found: {source}")
            shutil.copyfile(source, destination / filename)
    _verify_models(stage, payload)


def _install_new_tree(stage: Path, destination: Path, verifier: Any) -> None:
    if destination.exists():
        verifier(destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, destination)
    verifier(destination)


def _preflight_destination(destination: Path, verifier: Any) -> None:
    """Validate an existing target before either managed tree is installed."""
    if destination.exists():
        verifier(destination)


def provision(
    *,
    data_root: Path,
    model_root: Path,
    bundle: str | None,
    offline_bundle_dir: Path | None,
    verify_only: bool,
) -> None:
    data_root = _require_absolute(data_root, "data root")
    model_root = _require_absolute(model_root, "model root")
    if offline_bundle_dir is not None:
        offline_bundle_dir = _require_absolute(offline_bundle_dir, "offline bundle directory")
    data_manifest = load_json_object(DATA_MANIFEST)
    entries = data_entries(data_manifest)
    model_manifest = load_json_object(MODEL_MANIFEST)

    if verify_only:
        verify_files(data_root, entries, reject_unexpected=True)
        _verify_models(model_root, model_manifest)
        return
    if bundle is None:
        raise BundleError("--bundle is required unless --verify-only is used")

    with tempfile.TemporaryDirectory(prefix="thesisagent_provision_") as temporary_name:
        temporary = Path(temporary_name)
        archive_path = _archive_source(bundle, offline_bundle_dir, temporary)
        data_stage = temporary / "data-stage"
        data_stage.mkdir()
        _extract_archive(archive_path, data_stage, entries)
        model_stage = temporary / "model-stage"
        model_stage.mkdir()
        _stage_models(
            model_stage,
            model_manifest,
            offline_bundle_dir,
            temporary / "huggingface-download-cache",
        )
        data_verifier = lambda root: verify_files(
            root, entries, reject_unexpected=True
        )
        model_verifier = lambda root: _verify_models(root, model_manifest)
        # Avoid a partial cross-tree install when either pre-existing target is
        # invalid. Each newly installed tree is itself an atomic rename.
        _preflight_destination(data_root, data_verifier)
        _preflight_destination(model_root, model_verifier)
        _install_new_tree(
            data_stage,
            data_root,
            data_verifier,
        )
        _install_new_tree(
            model_stage,
            model_root,
            model_verifier,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--bundle")
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--offline-bundle-dir", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    provision(
        data_root=args.data_root,
        model_root=args.model_root,
        bundle=args.bundle,
        offline_bundle_dir=args.offline_bundle_dir,
        verify_only=args.verify_only,
    )


if __name__ == "__main__":
    main()
