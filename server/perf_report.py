"""Print performance-event percentiles from the shared usage-stats store.

Reads directly from the storage backend (STORAGE=local|s3), the same way
data_prep/data_upload.py talks to it - not through the Lambda HTTP API.

Usage:
    STORAGE=local PYTHONPATH=.. uv run python perf_report.py
    STORAGE=s3 DATA_BUCKET=... PYTHONPATH=.. uv run python perf_report.py
"""
from __future__ import annotations

import math
from collections import defaultdict

from python_lib.storage import backend as storage_backend

from handler import USAGE_STATS_KEY


def percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile (0-100) over an already-sorted list."""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, math.ceil(pct / 100 * len(sorted_values)) - 1)
    return sorted_values[max(0, idx)]


def flatten_batches(batches: list[dict]) -> list[dict]:
    """Flatten stored {client, receivedAt, events: [...]} batches into a
    single list of events, for grouping regardless of which batch/client
    each one came from."""
    events = []
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        batch_events = batch.get("events")
        if isinstance(batch_events, list):
            events.extend(e for e in batch_events if isinstance(e, dict))
    return events


def group_durations(events: list[dict]) -> dict[str, list[float]]:
    """Bucket event durations (ms) by event name."""
    grouped = defaultdict(list)
    for event in events:
        if not isinstance(event, dict):
            continue
        name = event.get("name")
        duration = event.get("durationMs")
        if not isinstance(name, str) or not isinstance(duration, (int, float)):
            continue
        grouped[name].append(float(duration))
    return grouped


def print_report(events: list[dict]) -> None:
    """Print count and p10/p50/p90 duration per event name."""
    if not events:
        print("No performance events stored.")
        return
    grouped = group_durations(events)
    print(f"{'event':<28} {'count':>7} {'p10':>9} {'p50':>9} {'p90':>9}")
    for name in sorted(grouped):
        values = sorted(grouped[name])
        p10 = percentile(values, 10)
        p50 = percentile(values, 50)
        p90 = percentile(values, 90)
        print(f"{name:<28} {len(values):>7} {p10:>8.0f}ms {p50:>8.0f}ms {p90:>8.0f}ms")


def main() -> None:
    """Read the shared usage-stats blob from the active backend and report."""
    backend = storage_backend.get_backend()
    batches = _read_json_or_default(backend, USAGE_STATS_KEY, [])
    print(f"Source: {backend.get_location(USAGE_STATS_KEY)}")
    print_report(flatten_batches(batches))


def _read_json_or_default(backend, key: str, default):
    if not backend.exists(key):
        return default
    return backend.read_json(key)


if __name__ == "__main__":
    main()
