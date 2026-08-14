import perf_report


def test_percentile_basic():
    values = list(range(1, 11))  # 1..10
    assert perf_report.percentile(values, 50) == 5
    assert perf_report.percentile(values, 90) == 9
    assert perf_report.percentile(values, 10) == 1


def test_percentile_empty():
    assert perf_report.percentile([], 50) == 0.0


def test_flatten_batches_pulls_events_out_of_each_batch():
    batches = [
        {
            "client": {"os": "macOS"},
            "receivedAt": "t1",
            "events": [{"name": "a", "durationMs": 1}],
        },
        {
            "client": {"os": "Windows"},
            "receivedAt": "t2",
            "events": [{"name": "b", "durationMs": 2}],
        },
        "not-a-dict",
        {"client": {}, "receivedAt": "t3", "events": "not-a-list"},
        {
            "client": {},
            "receivedAt": "t4",
            "events": [{"name": "c", "durationMs": 3}, "not-a-dict"],
        },
    ]
    events = perf_report.flatten_batches(batches)
    assert [e["name"] for e in events] == ["a", "b", "c"]


def test_group_durations_ignores_malformed_entries():
    events = [
        {"name": "a", "durationMs": 10},
        {"name": "a", "durationMs": 20},
        {"name": "b", "durationMs": 5},
        {"name": "no_duration"},
        {"durationMs": 5},
        "not-a-dict",
    ]
    grouped = perf_report.group_durations(events)
    assert grouped["a"] == [10.0, 20.0]
    assert grouped["b"] == [5.0]
    assert set(grouped.keys()) == {"a", "b"}
