import json

import python_lib.storage.backend as storage_backend

import handler


def make_event_with_token(token: str, body: str | None = None):
    ev = {"headers": {"Authorization": f"Bearer {token}"}}
    if body is not None:
        ev["body"] = body
    return ev


class DummyBackend:
    def __init__(self, initial=None):
        self.store = dict(initial or {})

    def exists(self, key):
        return key in self.store

    def read_bytes(self, key):
        return self.store[key]

    def write_bytes(self, key, data):
        self.store[key] = data


def test_merge_observations_delete_wins_over_newer_server_edit(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user1"})
    initial = [
        {
            "date": "2026-01-01",
            "note": "server edit",
            "updatedAt": "2026-01-02T00:00:00.000Z",
        },
        {
            "date": "2026-01-03",
            "note": "untouched",
            "updatedAt": "2026-01-01T00:00:00.000Z",
        },
    ]
    backend = DummyBackend(
        {"observations/user1.json": json.dumps(initial).encode("utf-8")}
    )
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    body = json.dumps({"upserts": [], "deletes": ["2026-01-01"]})
    res = handler.handle_merge_observations(make_event_with_token("tok", body=body))
    assert res["statusCode"] == 200
    merged = json.loads(res["body"])
    assert [o["date"] for o in merged] == ["2026-01-03"]


def test_merge_observations_newest_upsert_wins(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user2"})
    initial = [
        {"date": "2026-01-01", "note": "old", "updatedAt": "2026-01-01T00:00:00.000Z"}
    ]
    backend = DummyBackend(
        {"observations/user2.json": json.dumps(initial).encode("utf-8")}
    )
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    upsert = {
        "date": "2026-01-01",
        "note": "new",
        "updatedAt": "2026-01-02T00:00:00.000Z",
    }
    body = json.dumps({"upserts": [upsert], "deletes": []})
    res = handler.handle_merge_observations(make_event_with_token("tok", body=body))
    assert res["statusCode"] == 200
    merged = json.loads(res["body"])
    assert merged == [upsert]


def test_merge_observations_older_upsert_dropped(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user3"})
    initial = [
        {
            "date": "2026-01-01",
            "note": "server-newer",
            "updatedAt": "2026-01-05T00:00:00.000Z",
        }
    ]
    backend = DummyBackend(
        {"observations/user3.json": json.dumps(initial).encode("utf-8")}
    )
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    upsert = {
        "date": "2026-01-01",
        "note": "client-older",
        "updatedAt": "2026-01-02T00:00:00.000Z",
    }
    body = json.dumps({"upserts": [upsert], "deletes": []})
    res = handler.handle_merge_observations(make_event_with_token("tok", body=body))
    assert res["statusCode"] == 200
    merged = json.loads(res["body"])
    assert merged == initial


def test_merge_observations_no_existing_data(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user4"})
    backend = DummyBackend()
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    upsert = {
        "date": "2026-02-01",
        "note": "brand new",
        "updatedAt": "2026-02-01T00:00:00.000Z",
    }
    body = json.dumps({"upserts": [upsert], "deletes": []})
    res = handler.handle_merge_observations(make_event_with_token("tok", body=body))
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == [upsert]


def test_merge_finding_paths_delete_and_upsert(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user5"})
    initial = {
        "dso_M042": {
            "677": {
                "steps": [{"final": True}],
                "updatedAt": "2026-01-01T00:00:00.000Z",
            },
            "999": {
                "steps": [{"final": True}],
                "updatedAt": "2026-01-01T00:00:00.000Z",
            },
        }
    }
    backend = DummyBackend(
        {"finding-paths/user5.json": json.dumps(initial).encode("utf-8")}
    )
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    body = json.dumps(
        {
            "upserts": [
                {
                    "objectId": "dso_M042",
                    "startHip": "677",
                    "steps": [{"final": True}],
                    "updatedAt": "2026-01-03T00:00:00.000Z",
                }
            ],
            "deletes": ["dso_M042::999"],
        }
    )
    res = handler.handle_merge_finding_paths(make_event_with_token("tok", body=body))
    assert res["statusCode"] == 200
    merged = json.loads(res["body"])
    assert list(merged["dso_M042"].keys()) == ["677"]
    assert merged["dso_M042"]["677"]["updatedAt"] == "2026-01-03T00:00:00.000Z"


def test_merge_finding_paths_delete_last_entry_removes_object(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user6"})
    initial = {
        "dso_M042": {
            "677": {"steps": [{"final": True}], "updatedAt": "2026-01-01T00:00:00.000Z"}
        }
    }
    backend = DummyBackend(
        {"finding-paths/user6.json": json.dumps(initial).encode("utf-8")}
    )
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    body = json.dumps({"upserts": [], "deletes": ["dso_M042::677"]})
    res = handler.handle_merge_finding_paths(make_event_with_token("tok", body=body))
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == {}


def test_merge_telescopes(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user7"})
    initial = [
        {"id": "tel1", "name": "8in Dob", "updatedAt": "2026-01-01T00:00:00.000Z"}
    ]
    backend = DummyBackend(
        {"telescopes/user7.json": json.dumps(initial).encode("utf-8")}
    )
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    upsert = {
        "id": "tel2",
        "name": "New scope",
        "updatedAt": "2026-01-02T00:00:00.000Z",
    }
    body = json.dumps({"upserts": [upsert], "deletes": ["tel1"]})
    res = handler._handle_merge_flat_list(
        make_event_with_token("tok", body=body),
        handler._telescopes_key_for_user,
        "id",
        "Telescopes",
    )
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == [upsert]


def test_get_and_save_eyepieces(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user8"})
    backend = DummyBackend()
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    res = handler._handle_get_flat_list(
        make_event_with_token("tok"), handler._eyepieces_key_for_user
    )
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == []

    items = [{"id": "eye1", "name": "25mm", "updatedAt": "2026-01-01T00:00:00.000Z"}]
    save_res = handler._handle_save_flat_list(
        make_event_with_token("tok", body=json.dumps(items)),
        handler._eyepieces_key_for_user,
        "Eyepieces",
    )
    assert save_res["statusCode"] == 200
    assert backend.store["eyepieces/user8.json"] == json.dumps(items).encode("utf-8")


def test_routes_registered_for_new_endpoints(monkeypatch):
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user9"})
    backend = DummyBackend()
    monkeypatch.setattr(storage_backend, "get_backend", lambda: backend)

    assert (
        handler._route_telescopes(
            "/telescopes", "GET", {"headers": {"Authorization": "Bearer tok"}}
        )
        is not None
    )
    assert (
        handler._route_eyepieces(
            "/eyepieces", "GET", {"headers": {"Authorization": "Bearer tok"}}
        )
        is not None
    )
    assert (
        handler._route_observations(
            "/observations/merge",
            "POST",
            make_event_with_token(
                "tok", body=json.dumps({"upserts": [], "deletes": []})
            ),
        )
        is not None
    )
    assert (
        handler._route_finding_paths(
            "/finding-paths/merge",
            "POST",
            make_event_with_token(
                "tok", body=json.dumps({"upserts": [], "deletes": []})
            ),
        )
        is not None
    )
