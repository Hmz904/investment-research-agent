"""Validate the interpreter and installed packages against the frozen lock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = PROJECT_ROOT / "packaging" / "frozen_environment_v0.1.json"
_PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)$")


class EnvironmentContractError(RuntimeError):
    """The active Python environment violates the frozen contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locked_versions(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        match = _PIN_RE.fullmatch(line)
        if match is None:
            raise EnvironmentContractError(
                f"non-exact requirement at {path}:{line_number}: {line!r}"
            )
        canonical_name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        if canonical_name in versions:
            raise EnvironmentContractError(f"duplicate locked package: {canonical_name}")
        versions[canonical_name] = match.group(2)
    if not versions:
        raise EnvironmentContractError("environment lock contains no packages")
    return versions


def verify_environment(contract_path: Path = DEFAULT_CONTRACT) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    lock_path = PROJECT_ROOT / str(contract["lock_file"])
    expected_lock_hash = str(contract["lock_file_sha256"])
    actual_lock_hash = _sha256(lock_path)
    if actual_lock_hash != expected_lock_hash:
        raise EnvironmentContractError(
            f"lock SHA-256 mismatch: expected={expected_lock_hash} actual={actual_lock_hash}"
        )

    expected_platform = contract["platform"]
    actual_python = platform.python_version()
    actual_implementation = platform.python_implementation()
    actual_os = platform.system()
    actual_machine = platform.machine()
    comparisons = {
        "python_version": (expected_platform["python_version"], actual_python),
        "python_implementation": (
            expected_platform["python_implementation"],
            actual_implementation,
        ),
        "operating_system": (expected_platform["operating_system"], actual_os),
        "machine": (expected_platform["machine"], actual_machine),
    }
    mismatches = [
        f"{name}: expected={expected!r} actual={actual!r}"
        for name, (expected, actual) in comparisons.items()
        if expected != actual
    ]
    if mismatches:
        raise EnvironmentContractError("platform mismatch: " + "; ".join(mismatches))

    package_mismatches: list[str] = []
    locked = _locked_versions(lock_path)
    for name, expected in sorted(locked.items()):
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            package_mismatches.append(f"{name}: missing (expected {expected})")
            continue
        if actual != expected:
            package_mismatches.append(
                f"{name}: expected={expected!r} actual={actual!r}"
            )
    if package_mismatches:
        raise EnvironmentContractError(
            "locked package mismatch: " + "; ".join(package_mismatches)
        )
    return {
        "environment_contract_version": contract["environment_contract_version"],
        "lock_file_sha256": actual_lock_hash,
        "locked_package_count": len(locked),
        "python_version": actual_python,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    print(json.dumps(verify_environment(args.contract), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
