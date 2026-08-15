import migrate_storage


class DummyBackend:
    def __init__(self, store=None):
        self.store = dict(store or {})

    def exists(self, key):
        return key in self.store

    def read_bytes(self, key):
        return self.store[key]

    def write_bytes(self, key, data):
        self.store[key] = data

    def delete_bytes(self, key):
        self.store.pop(key, None)

    def list_keys(self, prefix):
        return [k for k in self.store if k.startswith(prefix)]


OLD_KEY = "observations/uuid-1.json"
NEW_KEY = "users/alice/observations.json"


def test_migrate_key_copies_and_deletes_old():
    backend = DummyBackend({OLD_KEY: b"[1]"})
    status = migrate_storage.migrate_key(backend, OLD_KEY, NEW_KEY)
    assert status == f"migrated (from {OLD_KEY})"
    assert backend.store[NEW_KEY] == b"[1]"
    assert OLD_KEY not in backend.store


def test_migrate_key_not_found():
    backend = DummyBackend()
    status = migrate_storage.migrate_key(backend, OLD_KEY, NEW_KEY)
    assert status == "not found"
    assert backend.store == {}


def test_migrate_key_idempotent_when_already_migrated():
    backend = DummyBackend({OLD_KEY: b"[stale]", NEW_KEY: b"[current]"})
    status = migrate_storage.migrate_key(backend, OLD_KEY, NEW_KEY)
    assert status == "already migrated"
    # Neither side touched - old key is left for a human to clean up/inspect
    # rather than silently clobbering data that's already been migrated.
    assert backend.store[NEW_KEY] == b"[current]"
    assert backend.store[OLD_KEY] == b"[stale]"


def test_migrate_key_multi_tries_candidates_in_order():
    backend = DummyBackend({"app-data/performance/events.json": b"[2]"})
    status = migrate_storage.migrate_key_multi(
        backend,
        ["performance/events.json", "app-data/performance/events.json"],
        "users/_anonymized/performance.json",
    )
    assert status == "migrated (from app-data/performance/events.json)"
    assert backend.store["users/_anonymized/performance.json"] == b"[2]"
    assert "app-data/performance/events.json" not in backend.store


def test_migrate_key_multi_already_migrated():
    backend = DummyBackend({"users/_anonymized/performance.json": b"[current]"})
    status = migrate_storage.migrate_key_multi(
        backend, ["performance/events.json"], "users/_anonymized/performance.json"
    )
    assert status == "already migrated"


def test_migrate_key_multi_not_found():
    backend = DummyBackend()
    status = migrate_storage.migrate_key_multi(
        backend, ["performance/events.json"], "users/_anonymized/performance.json"
    )
    assert status == "not found"


def test_migrate_chunk_files_moves_top_level_matches_only():
    backend = DummyBackend(
        {
            "stars_t1_mag9.zip": b"a",
            "objects_mag12.zip": b"b",
            "t2_000_mag14.zip": b"c",
            "manifest.json": b"d",
            "app-data/t2_001_mag14.zip": b"e",
        }
    )
    results = migrate_storage.migrate_chunk_files(backend)
    assert dict(results) == {
        "stars_t1_mag9.zip": "migrated (from stars_t1_mag9.zip)",
        "objects_mag12.zip": "migrated (from objects_mag12.zip)",
        "t2_000_mag14.zip": "migrated (from t2_000_mag14.zip)",
    }
    assert backend.store["app-data/stars_t1_mag9.zip"] == b"a"
    assert backend.store["app-data/objects_mag12.zip"] == b"b"
    assert backend.store["app-data/t2_000_mag14.zip"] == b"c"
    assert "manifest.json" in backend.store
    assert backend.store["app-data/t2_001_mag14.zip"] == b"e"


def test_list_cognito_users_paginates_and_extracts_sub(monkeypatch):
    monkeypatch.setattr(migrate_storage, "COGNITO_USER_POOL_ID", "pool-123")

    class DummyPaginator:
        def paginate(self, UserPoolId):
            assert UserPoolId == "pool-123"
            alice_attrs = [
                {"Name": "sub", "Value": "uuid-1"},
                {"Name": "email", "Value": "a@x.com"},
            ]
            yield {"Users": [{"Username": "alice", "Attributes": alice_attrs}]}
            bob_attrs = [{"Name": "sub", "Value": "uuid-2"}]
            yield {
                "Users": [
                    {"Username": "bob", "Attributes": bob_attrs},
                    # missing sub attribute - should be skipped
                    {"Username": "no-sub", "Attributes": []},
                ]
            }

    class DummyClient:
        def get_paginator(self, name):
            assert name == "list_users"
            return DummyPaginator()

    class DummyBoto3:
        @staticmethod
        def client(*a, **k):
            return DummyClient()

    monkeypatch.setattr(migrate_storage, "boto3", DummyBoto3())

    users = migrate_storage.list_cognito_users()
    assert users == [("alice", "uuid-1"), ("bob", "uuid-2")]
