"""Rank tournament candidates using eval scores."""

from __future__ import annotations

from typing import Any


def rank_candidates(
    results: list[dict[str, Any]],
    *,
    direction: str = "minimize",
    primary_key: str = "primary",
) -> list[dict[str, Any]]:
    """Return survivors sorted best-first. Discards non-ok / reward_hack."""
    survivors = [
        r
        for r in results
        if r.get("ok") and not r.get("reward_hack") and r.get(primary_key) is not None
    ]

    def key(r: dict[str, Any]) -> float:
        v = float(r[primary_key])
        return v if direction == "minimize" else -v

    survivors.sort(key=key)
    return survivors


def pick_winner(
    results: list[dict[str, Any]],
    *,
    direction: str = "minimize",
    primary_key: str = "primary",
) -> dict[str, Any] | None:
    ranked = rank_candidates(results, direction=direction, primary_key=primary_key)
    return ranked[0] if ranked else None
