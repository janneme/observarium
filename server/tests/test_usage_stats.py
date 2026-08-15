import json

import python_lib.storage.backend as storage_backend

import handler


def make_event_with_token(token: str, body: str | None = None):
    ev = {"headers": {"Authorization": f"Bearer {token}"}}
    if body is not None:
        ev["body"] = body
    return ev


def test_save_usage_stats_requires_auth():
    ev = {"headers": {}, "body": json.dumps({"client": {}, "events": []})}
    res = handler.handle_save_usage_stats(ev)
    assert res["statusCode"] == 401


def test_save_usage_stats_rejects_malformed_body(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"username": "user1"})
    ev = make_event_with_token("tok", body=json.dumps({"events": "not-a-list"}))
    res = handler.handle_save_usage_stats(ev)
    assert res["statusCode"] == 400


def test_save_usage_stats_does_not_persist_username(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"username": "realuser"})

    saved: dict = {}

    class DummyBackend:
        def exists(self, key):
            return False

        def write_bytes(self, key, data):
            saved["key"] = key
            saved["data"] = data

    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    payload = {
        "client": {"catalogueMag": 12},
        "events": [
            {
                "name": "skyview_move_zoom",
                "durationMs": 842,
                "ts": "2026-08-14T21:00:00.000Z",
            }
        ],
    }
    ev = make_event_with_token("tok", body=json.dumps(payload))
    res = handler.handle_save_usage_stats(ev)
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == {"stored": 1}
    assert saved["key"] == handler.USAGE_STATS_KEY
    stored = json.loads(saved["data"])
    # One batch, client info attached once - not duplicated onto the event.
    assert len(stored) == 1
    batch = stored[0]
    assert batch["client"] == {"catalogueMag": 12}
    assert "receivedAt" in batch
    assert len(batch["events"]) == 1
    assert batch["events"][0]["name"] == "skyview_move_zoom"
    assert "client" not in batch["events"][0]
    # The whole point of anonymizing at the storage level: nothing in the
    # persisted record should mention the authenticated username.
    assert "realuser" not in json.dumps(stored)


def test_save_usage_stats_appends_and_prunes_old_batches(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"username": "user2"})
    monkeypatch.setattr(handler, "PERF_RETENTION_DAYS", 7)

    # Retention prunes whole batches (each upload is stamped with one
    # receivedAt), not individual events within a batch.
    existing = [
        {
            "client": {},
            "receivedAt": "2000-01-01T00:00:00+00:00",
            "events": [{"name": "old_event", "durationMs": 1}],
        },
        {
            "client": {},
            "receivedAt": "2100-01-01T00:00:00+00:00",
            "events": [{"name": "recent_event", "durationMs": 2}],
        },
    ]

    class DummyBackend:
        def __init__(self):
            self.stored = None

        def exists(self, key):
            return True

        def read_bytes(self, key):
            return json.dumps(existing).encode("utf-8")

        def write_bytes(self, key, data):
            self.stored = data

    backend = DummyBackend()
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    payload = {"client": {}, "events": [{"name": "new_event", "durationMs": 3}]}
    ev = make_event_with_token("tok", body=json.dumps(payload))
    res = handler.handle_save_usage_stats(ev)
    assert res["statusCode"] == 200

    stored = json.loads(backend.stored.decode("utf-8"))
    names = {e["name"] for batch in stored for e in batch["events"]}
    # old_event's batch is stamped from year 2000, well past a 7-day
    # retention window - the whole batch must be pruned. recent_event's
    # batch is stamped far in the future so it survives regardless of when
    # the test runs.
    assert "old_event" not in names
    assert "recent_event" in names
    assert "new_event" in names
