import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import python_lib.storage.backend as storage_backend

import handler


def test_build_response_headers():
    res = handler.build_response(200, {"ok": True})
    assert res["statusCode"] == 200
    assert "Access-Control-Allow-Origin" in res["headers"]
    body = json.loads(res["body"])
    assert body["ok"] is True


def test_get_bearer_token_from_event_variants():
    ev = {"headers": {"Authorization": "Bearer abc"}}
    assert handler._get_bearer_token_from_event(ev) == "abc"

    ev = {"headers": {"authorization": "Bearer xyz"}}
    assert handler._get_bearer_token_from_event(ev) == "xyz"

    ev = {"headers": {}}
    assert handler._get_bearer_token_from_event(ev) is None


def test_handle_presign_key(monkeypatch):
    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")

    class DummyBackend:
        def generate_presigned_get(self, key, expires=300):
            assert key == "objects.zip"
            return "https://presigned.example/get"

    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    out = handler.handle_presign_key("objects.zip")
    assert out["url"].startswith("https://presigned.example")
    assert out["bucket"] == "test-bucket"
    assert out["key"] == "objects.zip"


def test_handle_data_hash(monkeypatch):
    class DummyBackend:
        def read_bytes(self, key):
            if key == "manifest.hash":
                return b"abc123\n"
            raise FileNotFoundError(key)

    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")
    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    out = handler.handle_data_hash()
    assert out["hash"] == "abc123"


def test_handle_data_hash_missing(monkeypatch):
    class DummyBackend:
        def read_bytes(self, key):
            raise FileNotFoundError(key)

    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")
    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    out = handler.handle_data_hash()
    assert out["hash"] is None
