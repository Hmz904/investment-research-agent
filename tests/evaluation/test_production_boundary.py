"""Guard the production/evaluation dependency and file-access boundary."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
RETRIEVAL_RUNNERS = (
    ROOT / "evaluation" / "run_bm25.py",
    ROOT / "evaluation" / "run_embedding.py",
)
FORBIDDEN_PATHS = (
    "benchmark/frozen/",
    "benchmark/releases/",
    "benchmark/provenance/",
    "benchmark/errata/",
)
FORBIDDEN_FILENAMES = (
    "numeric_answers.csv",
    "evidence_checklist.csv",
    "score_retrieval.py",
    "bm25_v0.1_scores.json",
    "bm25_v0.1_per_question.csv",
    "bm25_v0.1_misses.csv",
)
FORBIDDEN_GOLD_MARKERS = (
    "gold-map",
    "gold_map",
    "source-anchor",
    "source_anchor",
)


def _imports(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _literal_path_parts(node: ast.AST) -> list[str]:
    """Recover constant components from common pathlib path expressions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [part for part in node.value.replace("\\", "/").split("/") if part]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _literal_path_parts(node.left) + _literal_path_parts(node.right)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "Path":
            return [part for arg in node.args for part in _literal_path_parts(arg)]
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            return _literal_path_parts(node.func.value) + [
                part for arg in node.args for part in _literal_path_parts(arg)
            ]
    return []


def test_src_has_no_gold_or_evaluation_dependency() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for module in _imports(tree):
            if module == "evaluation" or module.startswith("evaluation."):
                violations.append(f"{path}: imports {module}")
            if "provenance" in module.split("."):
                violations.append(f"{path}: imports gold tooling {module}")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            normalized = node.value.replace("\\", "/").lower()
            for forbidden in FORBIDDEN_PATHS:
                if forbidden in normalized:
                    violations.append(f"{path}: contains forbidden gold path {forbidden}")
            for forbidden in FORBIDDEN_FILENAMES:
                if forbidden in normalized:
                    violations.append(f"{path}: contains forbidden gold filename {forbidden}")
            for forbidden in FORBIDDEN_GOLD_MARKERS:
                if forbidden in normalized:
                    violations.append(f"{path}: contains forbidden gold marker {forbidden}")
            if normalized.endswith("_reviewed.csv"):
                violations.append(f"{path}: contains forbidden reviewed filename")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target: ast.AST | None = None
            if isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
                target = node.args[0]
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {
                "open", "read_text", "read_bytes"
            }:
                target = node.func.value
            if target is None:
                continue
            literal_path = "/".join(_literal_path_parts(target)).lower() + "/"
            for forbidden in FORBIDDEN_PATHS:
                if forbidden in literal_path:
                    violations.append(f"{path}: reads forbidden gold path {forbidden}")
            for forbidden in FORBIDDEN_FILENAMES:
                if forbidden in literal_path:
                    violations.append(f"{path}: reads forbidden gold filename {forbidden}")
            if literal_path.endswith("_reviewed.csv/"):
                violations.append(f"{path}: reads forbidden reviewed filename")
    assert violations == []


def test_no_provenance_module_remains_under_src() -> None:
    assert not (SRC / "provenance.py").exists()


def test_retrieval_runners_have_no_gold_input_dependency() -> None:
    violations: list[str] = []
    for runner in RETRIEVAL_RUNNERS:
        source = runner.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(runner))
        for module in _imports(tree):
            if "provenance" in module.split("."):
                violations.append(f"{runner}: imports gold tooling {module}")
            if module == "evaluation.score_retrieval":
                violations.append(f"{runner}: imports gold scorer {module}")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            normalized = node.value.replace("\\", "/").lower()
            for forbidden in FORBIDDEN_PATHS:
                if forbidden in normalized:
                    violations.append(
                        f"{runner}: contains forbidden gold path {forbidden}"
                    )
            for forbidden in FORBIDDEN_FILENAMES:
                if forbidden in normalized:
                    violations.append(
                        f"{runner}: contains forbidden gold filename {forbidden}"
                    )
            for forbidden in FORBIDDEN_GOLD_MARKERS:
                if forbidden in normalized:
                    violations.append(
                        f"{runner}: contains forbidden gold marker {forbidden}"
                    )
            if normalized.endswith("_reviewed.csv"):
                violations.append(f"{runner}: contains forbidden reviewed filename")
    assert violations == []
