import json

import user_export
import user_import


class DummyBackend:
    def __init__(self, store=None):
        self.store = dict(store or {})

    def exists(self, key):
        return key in self.store

    def read_bytes(self, key):
        return self.store[key]

    def write_bytes(self, key, data):
        self.store[key] = data

    def get_location(self, key):
        return f"dummy://{key}"


def test_export_user_writes_present_categories_and_skips_missing(monkeypatch, tmp_path):
    backend = DummyBackend(
        {
            "users/alice/observations.json": b'[{"date":"2026-01-01"}]',
            "users/alice/telescopes.json": b"[]",
            # finding-paths/eyepieces/lists intentionally absent
        }
    )
    monkeypatch.setattr("user_export.storage_backend.get_backend", lambda: backend)

    out_dir = tmp_path / "alice"
    results = user_export.export_user("alice", out_dir=out_dir)

    assert results["observations"] == "exported"
    assert results["telescopes"] == "exported"
    assert results["finding-paths"] == "not found"
    assert results["eyepieces"] == "not found"
    assert results["lists"] == "not found"

    assert (out_dir / "observations.json").read_text() == (
        json.dumps([{"date": "2026-01-01"}], indent=2) + "\n"
    )
    assert (out_dir / "telescopes.json").read_text() == json.dumps([], indent=2) + "\n"
    assert not (out_dir / "finding-paths.json").exists()


def test_find_local_files_only_returns_present_categories(tmp_path):
    (tmp_path / "observations.json").write_text("[]")
    (tmp_path / "lists.json").write_text("[]")
    (tmp_path / "not-a-category.json").write_text("[]")

    found = user_import.find_local_files("bob", in_dir=tmp_path)

    assert set(found.keys()) == {"observations", "lists"}
    assert found["observations"] == tmp_path / "observations.json"


def test_import_user_overwrites_remote_keys(monkeypatch, tmp_path):
    backend = DummyBackend()
    monkeypatch.setattr("user_import.storage_backend.get_backend", lambda: backend)

    (tmp_path / "observations.json").write_bytes(b'[{"date":"2026-02-02"}]')
    local_files = user_import.find_local_files("carol", in_dir=tmp_path)

    results = user_import.import_user("carol", local_files)

    assert results == {"observations": "imported"}
    assert backend.store["users/carol/observations.json"] == b'[{"date":"2026-02-02"}]'


OBS_KEY = "users/dave/observations.json"
LISTS_KEY = "users/dave/lists.json"


def test_export_then_import_round_trip(monkeypatch, tmp_path):
    remote = {
        OBS_KEY: json.dumps([{"date": "2026-03-03"}]).encode("utf-8"),
        LISTS_KEY: json.dumps([{"id": "l1"}]).encode("utf-8"),
    }
    export_backend = DummyBackend(remote)
    monkeypatch.setattr(
        "user_export.storage_backend.get_backend", lambda: export_backend
    )

    export_dir = tmp_path / "users" / "dave"
    user_export.export_user("dave", out_dir=export_dir)

    # Simulate the remote having drifted since export - import must overwrite
    # it back to exactly what was exported.
    import_backend = DummyBackend({OBS_KEY: b"[]", LISTS_KEY: b"[]"})
    monkeypatch.setattr(
        "user_import.storage_backend.get_backend", lambda: import_backend
    )

    local_files = user_import.find_local_files("dave", in_dir=export_dir)
    user_import.import_user("dave", local_files)

    # Import writes back the pretty-printed export file verbatim, so compare
    # parsed content rather than raw bytes (formatting differs, data doesn't).
    assert json.loads(import_backend.store[OBS_KEY]) == json.loads(remote[OBS_KEY])
    assert json.loads(import_backend.store[LISTS_KEY]) == json.loads(remote[LISTS_KEY])
