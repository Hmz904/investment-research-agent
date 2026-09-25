"""Pinned logical model payload identities and local-path resolution."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .frozen_data import (
    FrozenDataHashError,
    FrozenDataMissingError,
    FrozenDataPathError,
    normalize_explicit_root,
    sha256_file,
)


BASE_MODEL_ID = "BAAI/bge-base-en-v1.5"
BASE_MODEL_REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
RERANKER_MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"

BASE_MODEL_FILES: Mapping[str, tuple[int, str]] = {
    "config.json": (777, "bc00af31a4a31b74040d73370aa83b62da34c90b75eb77bfa7db039d90abd591"),
    "model.safetensors": (437955512, "c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7"),
    "special_tokens_map.json": (125, "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3"),
    "tokenizer.json": (711396, "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"),
    "tokenizer_config.json": (366, "9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3"),
    "vocab.txt": (231508, "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3"),
}

RERANKER_MODEL_FILES: Mapping[str, tuple[int, str]] = {
    "config.json": (795, "13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a"),
    "model.safetensors": (2271071852, "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"),
    "sentencepiece.bpe.model": (5069051, "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"),
    "special_tokens_map.json": (964, "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835"),
    "tokenizer.json": (17098273, "69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15"),
    "tokenizer_config.json": (1173, "7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4"),
}


def model_payload_directory(model_root: str | Path, model_id: str, revision: str) -> Path:
    root = normalize_explicit_root(model_root, label="frozen model root")
    logical = root / model_id.replace("/", "--") / revision
    legacy_cache = root / f"models--{model_id.replace('/', '--')}" / "snapshots" / revision
    if logical.is_dir():
        selected = logical.resolve()
    elif legacy_cache.is_dir():
        selected = legacy_cache.resolve()
    else:
        raise FrozenDataMissingError(
            f"missing provisioned model payload for {model_id}@{revision} beneath {root}"
        )
    if not selected.is_relative_to(root):
        raise FrozenDataPathError(f"model payload escapes explicit model root: {selected}")
    return selected


def verify_model_payload(
    directory: Path,
    files: Mapping[str, tuple[int, str]],
    *,
    containment_root: Path | None = None,
) -> None:
    allowed_root = (directory if containment_root is None else containment_root).resolve()
    for filename, (expected_size, expected_hash) in sorted(files.items()):
        path = (directory / filename).resolve(strict=False)
        if not path.is_relative_to(allowed_root):
            raise FrozenDataPathError(f"model file escapes payload directory: {filename}")
        if not path.is_file():
            raise FrozenDataMissingError(f"missing frozen model file: {path}")
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise FrozenDataHashError(
                f"frozen model size mismatch for {path}: "
                f"expected={expected_size} actual={actual_size}"
            )
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise FrozenDataHashError(
                f"frozen model SHA-256 mismatch for {path}: "
                f"expected={expected_hash} actual={actual_hash}"
            )
