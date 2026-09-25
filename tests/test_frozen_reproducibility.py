"""Gold-blind contracts for provisioned frozen data and model roots."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from scripts.frozen_bundle import BundleError, sha256_file, verify_files
from scripts.provision_frozen_data import _extract_archive, provision
from scripts.verify_frozen_environment import verify_environment
from src.frozen_data import (
    FrozenDataHashError,
    FrozenDataMissingError,
    FrozenDataPathError,
    resolve_raw_document,
)
from src.frozen_models import verify_model_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _entry(doc_id: str, historical: Path, content: bytes) -> dict[str, object]:
    return {
        "doc_id": doc_id,
        "local_path": str(historical),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def test_provisioned_root_wins_and_historical_path_is_never_read(
    tmp_path: Path,
) -> None:
    content = b"provisioned"
    doc_id = "issuer-2025-10-k"
    historical = tmp_path / "historical" / f"{doc_id}.htm"
    historical.parent.mkdir()
    historical.write_bytes(b"wrong historical bytes")
    data_root = tmp_path / "relocated"
    (data_root / "raw").mkdir(parents=True)
    candidate = data_root / "raw" / f"{doc_id}.htm"
    candidate.write_bytes(content)

    assert resolve_raw_document(
        data_root=data_root.resolve(),
        manifest_entry=_entry(doc_id, historical, content),
    ) == candidate.resolve()


def test_raw_resolver_rejects_escape_basename_suffix_hash_and_missing(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "doc.htm").write_bytes(b"ok")
    data_root.mkdir()
    (data_root / "raw").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FrozenDataPathError, match="escapes"):
        resolve_raw_document(
            data_root=data_root.resolve(),
            manifest_entry=_entry("doc", Path("/old/doc.htm"), b"ok"),
        )

    (data_root / "raw").unlink()
    (data_root / "raw").mkdir()
    (data_root / "raw" / "doc.htm").write_bytes(b"bad")
    with pytest.raises(FrozenDataPathError, match="basename mismatch"):
        resolve_raw_document(
            data_root=data_root.resolve(),
            manifest_entry=_entry("doc", Path("/old/not-doc.htm"), b"bad"),
        )
    with pytest.raises(FrozenDataPathError, match="suffix"):
        resolve_raw_document(
            data_root=data_root.resolve(),
            manifest_entry=_entry("doc", Path("/old/doc.xml"), b"bad"),
        )
    with pytest.raises(FrozenDataHashError, match="SHA-256 mismatch"):
        resolve_raw_document(
            data_root=data_root.resolve(),
            manifest_entry=_entry("doc", Path("/old/doc.htm"), b"expected"),
        )
    (data_root / "raw" / "doc.htm").unlink()
    with pytest.raises(FrozenDataMissingError, match="missing provisioned"):
        resolve_raw_document(
            data_root=data_root.resolve(),
            manifest_entry=_entry("doc", Path("/old/doc.htm"), b"expected"),
        )


def test_relocated_xbrl_tool_uses_only_explicit_root(tmp_path: Path) -> None:
    from src.tools.xbrl_tool import XBRLTool

    source = PROJECT_ROOT / "data"
    relocated = tmp_path / "relocated-data"
    shutil.copytree(source / "raw", relocated / "raw")
    shutil.copytree(source / "parsed", relocated / "parsed")
    shutil.copytree(source / "chunks", relocated / "chunks")
    shutil.copy2(source / "manifest.json", relocated / "manifest.json")
    before = (relocated / "manifest.json").read_bytes()
    tool = XBRLTool.from_frozen_ingestion(data_root=relocated.resolve())
    assert tool.fact_count > 0
    assert (relocated / "manifest.json").read_bytes() == before


def test_relocated_frozen_pipeline_reuses_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.pipeline as pipeline
    from src.corpus import SOURCES

    source_root = PROJECT_ROOT / "data"
    manifest = json.loads((source_root / "manifest.json").read_text(encoding="utf-8"))
    source = dict(SOURCES[0])
    manifest_entry = next(row for row in manifest["entries"] if row["doc_id"] == source["doc_id"])
    relocated = tmp_path / "pipeline-data"
    for name in ("raw", "parsed", "chunks"):
        (relocated / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / "manifest.json", relocated / "manifest.json")
    shutil.copy2(
        source_root / "raw" / f"{source['doc_id']}.htm",
        relocated / "raw" / f"{source['doc_id']}.htm",
    )
    monkeypatch.setattr(pipeline, "SOURCES", [source])
    monkeypatch.setattr(
        pipeline,
        "SECClient",
        lambda: (_ for _ in ()).throw(AssertionError("network client constructed")),
    )
    summary = pipeline.run(data_root=relocated.resolve(), mode="frozen")
    assert summary["documents"] == 1
    assert summary["downloaded_raw_files"] == 0
    assert sha256_file(relocated / "parsed" / f"{source['doc_id']}.json") == manifest_entry["parsed_sha256"]
    assert sha256_file(relocated / "chunks" / f"{source['doc_id']}.json") == manifest_entry["chunk_sha256"]


def test_model_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    payload = tmp_path / "model"
    payload.mkdir()
    (payload / "config.json").write_bytes(b"wrong")
    with pytest.raises(FrozenDataHashError, match="size mismatch|SHA-256 mismatch"):
        verify_model_payload(
            payload,
            {"config.json": (5, hashlib.sha256(b"right").hexdigest())},
        )


def _tar(path: Path, members: list[tuple[str, bytes, str]]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                archive.addfile(info)
            else:  # pragma: no cover - test helper misuse
                raise AssertionError(kind)


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ([("/absolute", b"x", "file")], "unsafe bundle path"),
        ([("../escape", b"x", "file")], "unsafe bundle path"),
        ([("raw/a", b"", "symlink")], "not a regular file"),
        ([("raw/a", b"x", "file"), ("raw/a", b"x", "file")], "duplicate"),
        ([("raw/A", b"x", "file"), ("raw/a", b"x", "file")], "case-colliding"),
    ],
)
def test_archive_rejects_unsafe_members(
    tmp_path: Path, members: list[tuple[str, bytes, str]], message: str
) -> None:
    archive = tmp_path / "bad.tar"
    _tar(archive, members)
    entries = [
        {"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        for name, content, kind in members
        if kind == "file" and ".." not in Path(name).parts
    ]
    with pytest.raises(BundleError, match=message):
        _extract_archive(archive, tmp_path / "stage", entries)


def test_bundle_missing_and_unexpected_files_are_rejected(tmp_path: Path) -> None:
    entries = [{"path": "raw/a.htm", "bytes": 1, "sha256": hashlib.sha256(b"a").hexdigest()}]
    with pytest.raises(BundleError, match="missing"):
        verify_files(tmp_path, entries, reject_unexpected=True)
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.htm").write_bytes(b"a")
    (tmp_path / "raw" / "extra.htm").write_bytes(b"x")
    with pytest.raises(BundleError, match="unexpected"):
        verify_files(tmp_path, entries, reject_unexpected=True)


def test_missing_frozen_pipeline_input_never_constructs_network_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.pipeline as pipeline

    data_root = tmp_path / "missing-input"
    for name in ("raw", "parsed", "chunks"):
        (data_root / name).mkdir(parents=True, exist_ok=True)
    (data_root / "manifest.json").write_text('{"entries": []}', encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "SOURCES",
        [{"doc_id": "missing-doc"}],
    )
    monkeypatch.setattr(
        pipeline,
        "SECClient",
        lambda: (_ for _ in ()).throw(AssertionError("network client constructed")),
    )
    with pytest.raises(RuntimeError, match="missing provisioned frozen input"):
        pipeline.run(data_root=data_root.resolve(), mode="frozen")


def test_provisioning_is_idempotent_and_verify_only_is_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.provision_frozen_data as module

    data_content = b"manifest"
    data_manifest = {
        "file_count": 1,
        "total_bytes": len(data_content),
        "files": [{"path": "manifest.json", "bytes": len(data_content), "sha256": hashlib.sha256(data_content).hexdigest()}],
    }
    aggregate_line = f"{data_manifest['files'][0]['sha256']}  manifest.json\n".encode()
    data_manifest["aggregate_sha256"] = hashlib.sha256(aggregate_line).hexdigest()

    models = []
    for model_index in range(2):
        files = []
        for file_index in range(6):
            content = f"m{model_index}-{file_index}".encode()
            files.append({"path": f"f{file_index}", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        models.append({"model_id": f"org/model-{model_index}", "revision": f"rev-{model_index}", "files": files})
    model_manifest = {
        "file_count": 12,
        "total_bytes": sum(row["bytes"] for model in models for row in model["files"]),
        "models": models,
    }

    offline = tmp_path / "offline"
    offline.mkdir()
    asset = offline / "bundle.tar"
    _tar(asset, [("manifest.json", data_content, "file")])
    for model in models:
        directory = offline / "models" / model["model_id"].replace("/", "--") / model["revision"]
        directory.mkdir(parents=True)
        for row in model["files"]:
            (directory / row["path"]).write_bytes(f"m{models.index(model)}-{int(row['path'][1:])}".encode())

    data_manifest_path = tmp_path / "data-manifest.json"
    model_manifest_path = tmp_path / "model-manifest.json"
    release_manifest_path = tmp_path / "release.json"
    data_manifest_path.write_text(json.dumps(data_manifest), encoding="utf-8")
    model_manifest_path.write_text(json.dumps(model_manifest), encoding="utf-8")
    release_manifest_path.write_text(json.dumps({
        "asset_name": asset.name,
        "archive_sha256": sha256_file(asset),
        "archive_bytes": asset.stat().st_size,
        "future_release_tag": "immutable-v1",
    }), encoding="utf-8")
    monkeypatch.setattr(module, "DATA_MANIFEST", data_manifest_path)
    monkeypatch.setattr(module, "MODEL_MANIFEST", model_manifest_path)
    monkeypatch.setattr(module, "RELEASE_MANIFEST", release_manifest_path)

    data_root = (tmp_path / "installed-data").resolve()
    model_root = (tmp_path / "installed-models").resolve()
    kwargs = dict(data_root=data_root, model_root=model_root, bundle=asset.name, offline_bundle_dir=offline.resolve())
    provision(**kwargs, verify_only=False)
    first = {p.relative_to(tmp_path).as_posix(): sha256_file(p) for p in tmp_path.rglob("*") if p.is_file()}
    provision(**kwargs, verify_only=False)
    provision(**kwargs, verify_only=True)
    second = {p.relative_to(tmp_path).as_posix(): sha256_file(p) for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second


def test_environment_lock_identity_and_machine_path_hygiene() -> None:
    result = verify_environment()
    assert result["status"] == "PASS"
    for relative in (
        "packaging/frozen_runtime_bundle_v0.1.json",
        "packaging/frozen_model_payloads_v0.1.json",
        "packaging/frozen_environment_v0.1.json",
        "packaging/frozen_runtime_bundle_release_v0.1.json",
    ):
        content = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "/mnt/" not in content
        assert str(PROJECT_ROOT) not in content
