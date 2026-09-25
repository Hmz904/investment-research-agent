"""Build a byte-deterministic regular-file-only frozen data tar archive."""

from __future__ import annotations

import argparse
import io
import json
import tarfile
from pathlib import Path

try:
    from scripts.frozen_bundle import (
        data_entries,
        load_json_object,
        sha256_file,
        verify_files,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` invocation.
    from frozen_bundle import data_entries, load_json_object, sha256_file, verify_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "packaging" / "frozen_runtime_bundle_v0.1.json"


def build_archive(*, data_root: Path, manifest_path: Path, output: Path) -> dict[str, object]:
    manifest = load_json_object(manifest_path)
    entries = data_entries(manifest)
    verify_files(data_root, entries, reject_unexpected=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw_output:
        with tarfile.open(fileobj=raw_output, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for item in entries:
                source = data_root / str(item["path"])
                info = tarfile.TarInfo(str(item["path"]))
                info.size = int(item["bytes"])
                info.mode = 0o644
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.pax_headers = {}
                with source.open("rb") as handle:
                    archive.addfile(info, fileobj=handle)
    return {
        "archive": str(output),
        "archive_bytes": output.stat().st_size,
        "archive_sha256": sha256_file(output),
        "bundle_manifest_sha256": sha256_file(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.data_root.is_absolute() or not args.output.is_absolute():
        raise SystemExit("--data-root and --output must be absolute paths")
    result = build_archive(
        data_root=args.data_root,
        manifest_path=args.manifest,
        output=args.output,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
