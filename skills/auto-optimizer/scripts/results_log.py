"""Append experiment results to results.tsv and results.jsonl."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import results_jsonl_path, results_tsv_path
from state import atomic_write_text


TSV_HEADER = [
    "timestamp",
    "cycle_id",
    "module",
    "status",
    "primary_metric",
    "primary_value",
    "baseline_value",
    "delta",
    "kept",
    "notes",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_results_files(hroot: Path) -> None:
    tsv = results_tsv_path(hroot)
    if not tsv.exists():
        atomic_write_text(tsv, "\t".join(TSV_HEADER) + "\n")
    j = results_jsonl_path(hroot)
    if not j.exists():
        j.write_text("", encoding="utf-8")


def append_result(hroot: Path, row: dict[str, Any]) -> None:
    ensure_results_files(hroot)
    ts = row.get("timestamp") or _utc_now()
    record = {
        "timestamp": ts,
        "cycle_id": row.get("cycle_id", ""),
        "module": row.get("module", ""),
        "status": row.get("status", ""),
        "primary_metric": row.get("primary_metric", ""),
        "primary_value": row.get("primary_value", ""),
        "baseline_value": row.get("baseline_value", ""),
        "delta": row.get("delta", ""),
        "kept": row.get("kept", False),
        "notes": row.get("notes", ""),
    }
    # TSV append
    tsv = results_tsv_path(hroot)
    with tsv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t", lineterminator="\n")
        w.writerow(record)
    # JSONL append
    jpath = results_jsonl_path(hroot)
    with jpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
