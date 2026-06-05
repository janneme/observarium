import json
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

# Ensure the server package root is on sys.path so `import handler` works when
# pytest is invoked from different working directories or via `uv run`.
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

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
    # Provide a fake s3 client that returns a predictable URL
    class DummyS3:
        def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
            assert ClientMethod == "put_object"
            assert Params["Key"] == "objects.zip"
            return "https://presigned.example/put"
    # Patch storage backend used by handler
    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")
    class DummyBackend:
        def generate_presigned_put(self, key, expires=300):
            assert key == "objects.zip"
            return "https://presigned.example/put"

    import python_lib.storage.backend as storage_backend

    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    out = handler.handle_presign_key("objects.zip")
    assert out["url"].startswith("https://presigned.example")
    assert out["bucket"] == "test-bucket"
    assert out["key"] == "objects.zip"


def test_handle_data_hash(monkeypatch):
    class DummyBackend:
        def get_hash(self, key):
            if key == "objects.zip":
                return "etag1"
            return None

    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")
    import python_lib.storage.backend as storage_backend
    monkeypatch.setattr(storage_backend, "get_backend", lambda: DummyBackend())

    out = handler.handle_data_hash()
    assert out["objects"] == "etag1"
    assert out["images"] is None
