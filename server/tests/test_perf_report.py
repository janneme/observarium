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


def test_print_report_includes_p99_and_max(capsys):
    events = [{"name": "a", "durationMs": d} for d in [1, 2, 3, 4, 5, 6, 7, 8, 9, 1000]]
    perf_report.print_report(events)
    out = capsys.readouterr().out
    assert "p99" in out
    assert "max" in out
    assert "1000ms" in out  # the spike survives into the max column


def test_print_raw_events_orders_by_duration_desc(capsys):
    events = [
        {"ts": "t1", "name": "slow", "durationMs": 500, "data": {"x": 1}},
        {"ts": "t2", "name": "fast", "durationMs": 10, "data": {}},
        {"ts": "t3", "name": "medium", "durationMs": 100, "data": {}},
    ]
    perf_report.print_raw_events(events, top_n=2)
    out_lines = capsys.readouterr().out.splitlines()
    body = [line for line in out_lines if "data=" in line]
    assert "slow" in body[0]
    assert "medium" in body[1]
    # top_n=2 excludes the third-slowest
    assert not any("fast" in line for line in body)
