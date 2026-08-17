"""Print performance-event percentiles from the shared usage-stats store.

Reads directly from the storage backend (STORAGE=local|s3), the same way
data_prep/data_upload.py talks to it - not through the Lambda HTTP API.

Usage:
    STORAGE=local PYTHONPATH=.. uv run python perf_report.py
    STORAGE=s3 DATA_BUCKET=... PYTHONPATH=.. uv run python perf_report.py
    STORAGE=s3 DATA_BUCKET=... PYTHONPATH=.. uv run python perf_report.py --raw [N]
        (also print the N slowest individual events with their data payload,
        default N=20)
"""
from __future__ import annotations

import math
import sys
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
    """Print count and p10/p50/p90/p99/max duration per event name.

    p90 alone hides real spikes - two events sharing the same p50/p90 can
    have very different worst cases, and it's the worst case (not the
    median) that a user actually notices as "serious lag". p99/max make
    those spikes visible instead of silently averaged away.
    """
    if not events:
        print("No performance events stored.")
        return
    grouped = group_durations(events)
    print(
        f"{'event':<28} {'count':>7} {'p10':>9} {'p50':>9}",
        f"{'p90':>9} {'p99':>9} {'max':>9}",
    )
    for name in sorted(grouped):
        values = sorted(grouped[name])
        p10 = percentile(values, 10)
        p50 = percentile(values, 50)
        p90 = percentile(values, 90)
        p99 = percentile(values, 99)
        worst = values[-1]
        print(
            f"{name:<28} {len(values):>7} {p10:>8.0f}ms {p50:>8.0f}ms "
            f"{p90:>8.0f}ms {p99:>8.0f}ms {worst:>8.0f}ms"
        )


def print_raw_events(events: list[dict], top_n: int) -> None:
    """Print the top_n slowest individual events, with their `data` payload,
    for digging into what made a specific spike slow."""
    ranked = sorted(events, key=lambda e: e.get("durationMs", 0), reverse=True)
    print(f"\n=== Top {top_n} slowest individual events ===")
    for event in ranked[:top_n]:
        print(
            f"{event.get('ts')}  {event.get('name'):<26} "
            f"{event.get('durationMs'):>7}ms  data={event.get('data')}"
        )


def main() -> None:
    """Read the shared usage-stats blob from the active backend and report.

    Pass --raw [N] to also print the N (default 20) slowest individual
    events with their data payload, for investigating specific spikes.
    """
    raw_n = None
    if "--raw" in sys.argv:
        idx = sys.argv.index("--raw")
        raw_n = 20
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            raw_n = int(sys.argv[idx + 1])

    backend = storage_backend.get_backend()
    batches = _read_json_or_default(backend, USAGE_STATS_KEY, [])
    print(f"Source: {backend.get_location(USAGE_STATS_KEY)}")
    events = flatten_batches(batches)
    print_report(events)
    if raw_n is not None:
        print_raw_events(events, raw_n)


def _read_json_or_default(backend, key: str, default):
    if not backend.exists(key):
        return default
    return backend.read_json(key)


if __name__ == "__main__":
    main()
