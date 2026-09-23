"""Shared pytest configuration."""

from __future__ import annotations


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--regenerate-snapshots",
        action="store_true",
        default=False,
        help="Regenerate the corpus_stats.json snapshot from current output.",
    )

