import json

import python_lib.storage.backend as storage_backend

import handler


def make_event_with_token(token: str, body: str | None = None):
    ev = {"headers": {"Authorization": f"Bearer {token}"}}
    if body is not None:
        ev["body"] = body
    return ev


def test_get_observations_not_found(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user1"})

    class DummyBackend:
        def exists(self, key):
            return False

    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    ev = make_event_with_token("tok")
    res = handler.handle_get_observations(ev)
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == []


def test_save_observations_success(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user2"})

    saved: dict = {}

    class DummyBackend:
        def write_bytes(self, key, data):
            saved["key"] = key
            saved["data"] = data

    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    arr = [{"date": "2026-01-01", "note": "obs"}]
    ev = make_event_with_token("tok", body=json.dumps(arr))
    res = handler.handle_save_observations(ev)
    assert res["statusCode"] == 200
    assert saved["key"] == "observations/user2.json"
    assert json.loads(saved["data"]) == arr


def test_delete_observation(monkeypatch):
    initial = [{"date": "2026-01-01", "x": 1}, {"date": "2026-02-01", "x": 2}]

    class DummyBackend:
        def __init__(self):
            self.stored = None

        def exists(self, key):
            return True

        def read_bytes(self, key):
            return json.dumps(initial).encode("utf-8")

        def write_bytes(self, key, data):
            self.stored = data

    backend = DummyBackend()
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user3"})

    ev = make_event_with_token("tok")
    res = handler.handle_delete_observation(ev, "2026-01-01")
    assert res["statusCode"] == 200
    saved = json.loads(backend.stored.decode("utf-8"))
    assert saved == [{"date": "2026-02-01", "x": 2}]
