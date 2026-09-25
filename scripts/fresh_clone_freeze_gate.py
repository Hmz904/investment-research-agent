"""Run the permanent frozen-stack gate in a randomized, offline fresh clone."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_HASHES = {
    "data/manifest.json": "8498751b5d862950c800f92904492cf332b099842000c475941ac6cd7f8c8339",
    "evaluation/dev/xbrl/dev_xbrl_map_v0.1.json": "f129bf95b8a3428922ca5b87171f61e7a15481fc34586c37e22dfa23d33a2a53",
    "evaluation/dev/xbrl/dev_xbrl_map_coverage_v0.1.json": "59ef14f5ed7ffa7ba3eaea42abcde8100759c43d8d0633b09d9d44c70a3796cc",
    "evaluation/xbrl/temporal_context_catalog_v0.1.json": "63f6ec4bcbe5319ad9d63fa2186fdc23b4b78cdf5d7df4ff10d179245d161478",
    "evaluation/xbrl/temporal_context_catalog_coverage_v0.1.json": "9fc6bb692c89fcbe49ff78db4ae4d93e9f66c15c65b43274cd09f950e5ed9979",
}


class FreezeGateError(RuntimeError):
    """A fresh-clone freeze invariant failed."""


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode:
        raise FreezeGateError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def _offline_environment(clone: Path, guard: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": os.pathsep.join((str(guard), str(clone))),
        }
    )
    for name in tuple(env):
        if name.lower().endswith("_proxy"):
            env.pop(name, None)
    return env


def run_gate(
    *, source: Path, ref: str, python: Path, offline_bundle_dir: Path, bundle: str
) -> dict[str, object]:
    source = source.resolve()
    offline_bundle_dir = offline_bundle_dir.resolve()
    if not python.is_absolute() or not python.is_file():
        raise FreezeGateError(f"Python interpreter must be an explicit file: {python}")
    if _run(["git", "status", "--porcelain"], cwd=source).strip():
        raise FreezeGateError("source repository is not clean")

    with tempfile.TemporaryDirectory(prefix="thesisagent_freeze_gate_") as temp_name:
        temporary = Path(temp_name)
        clone = temporary / f"clone-{secrets.token_hex(8)}"
        _run(
            ["git", "clone", "--no-local", "--no-hardlinks", str(source), str(clone)],
            cwd=temporary,
        )
        _run(["git", "checkout", "--detach", ref], cwd=clone)

        guard = temporary / "network-guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import ssl\n"
            "import socket\n"
            "def _blocked(*args, **kwargs):\n"
            "    raise RuntimeError('network disabled by fresh-clone freeze gate')\n"
            "class _BlockedSocket(socket.socket):\n"
            "    def connect(self, *args, **kwargs):\n"
            "        return _blocked(*args, **kwargs)\n"
            "    def connect_ex(self, *args, **kwargs):\n"
            "        return _blocked(*args, **kwargs)\n"
            "socket.socket = _BlockedSocket\n"
            "socket.create_connection = _blocked\n",
            encoding="utf-8",
        )
        env = _offline_environment(clone, guard)
        data_root = (clone / "data").resolve()
        model_root = (data_root / "frozen_models").resolve()

        _run([str(python), "scripts/verify_frozen_environment.py"], cwd=clone, env=env)
        _run(
            [
                str(python),
                "scripts/provision_frozen_data.py",
                "--data-root",
                str(data_root),
                "--bundle",
                bundle,
                "--model-root",
                str(model_root),
                "--offline-bundle-dir",
                str(offline_bundle_dir),
            ],
            cwd=clone,
            env=env,
        )
        _run(
            [
                str(python),
                "-c",
                "from src.tools.runtime import ToolRegistry; "
                f"ToolRegistry.from_frozen_tools(data_root={str(data_root)!r}, "
                f"model_root={str(model_root)!r})",
            ],
            cwd=clone,
            env=env,
        )
        _run(
            [
                str(python),
                "-m",
                "evaluation.build_temporal_context_catalog",
                "--check",
                "--data-root",
                str(data_root),
            ],
            cwd=clone,
            env=env,
        )
        _run(
            [
                str(python),
                "-m",
                "evaluation.materialize_dev_xbrl_map_v0_1",
                "--check",
                "--data-root",
                str(data_root),
            ],
            cwd=clone,
            env=env,
        )
        _run(
            [
                str(python),
                "-c",
                "from pathlib import Path; from src.pipeline import run; "
                f"run(data_root=Path({str(data_root)!r}), mode='frozen')",
            ],
            cwd=clone,
            env=env,
        )
        _run(
            [
                str(python),
                "scripts/provision_frozen_data.py",
                "--data-root",
                str(data_root),
                "--model-root",
                str(model_root),
                "--verify-only",
            ],
            cwd=clone,
            env=env,
        )
        _run(
            [str(python), "-m", "pytest", "-q", "-m", "not locked_test_data"],
            cwd=clone,
            env=env,
        )
        _run(
            [
                str(python),
                "-m",
                "evaluation.validate_retrieval_determinism",
                "--check",
                "--data-root",
                str(data_root),
                "--model-root",
                str(model_root),
            ],
            cwd=clone,
            env=env,
        )

        import hashlib

        for relative, expected in FROZEN_HASHES.items():
            actual = hashlib.sha256((clone / relative).read_bytes()).hexdigest()
            if actual != expected:
                raise FreezeGateError(
                    f"frozen hash mismatch for {relative}: expected={expected} actual={actual}"
                )
        if _run(["git", "diff", "--exit-code"], cwd=clone).strip():
            raise FreezeGateError("fresh-clone working tree changed")
        if _run(["git", "diff", "--cached", "--exit-code"], cwd=clone).strip():
            raise FreezeGateError("fresh-clone index changed")
        if _run(["git", "status", "--porcelain"], cwd=clone).strip():
            raise FreezeGateError("fresh clone contains untracked or modified tracked files")
        return {
            "clone_commit": _run(["git", "rev-parse", "HEAD"], cwd=clone).strip(),
            "frozen_hash_count": len(FROZEN_HASHES),
            "network_guard": "Python sockets disabled after offline provisioning inputs selected",
            "status": "PASS",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--offline-bundle-dir", type=Path, required=True)
    parser.add_argument("--bundle", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run_gate(
                source=args.source,
                ref=args.ref,
                python=args.python,
                offline_bundle_dir=args.offline_bundle_dir,
                bundle=args.bundle,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
