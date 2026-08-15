from pathlib import Path

import python_lib.storage.backend as backend


def test_local_backend_write_read(tmp_path):
    base = tmp_path / "observarium"
    b = backend.LocalBackend(base=base)

    # write bytes
    b.write_bytes("objects.zip", b"hello")
    assert b.exists("objects.zip")
    assert b.read_bytes("objects.zip") == b"hello"

    # write json
    obj = {"a": 1}
    b.write_json("meta.json", obj)
    assert b.read_json("meta.json") == obj

    # get_hash returns sha256 hex
    h = b.get_hash("objects.zip")
    assert isinstance(h, str) and len(h) == 64

    # presigned put is a file:// URL
    url = b.generate_presigned_put("images.zip")
    assert url.startswith("file://")
    # ensure path resolved under base
    p = Path(url[len("file://"):])
    assert base in p.parents or p.parent == base

    # delete_bytes removes the file; deleting a missing key doesn't raise
    b.delete_bytes("objects.zip")
    assert not b.exists("objects.zip")
    b.delete_bytes("objects.zip")


def test_s3_backend_calls(monkeypatch):
    calls = {}

    class DummyClient:
        def __init__(self):
            self.storage = {"objects.zip": b"data"}

        def get_object(self, Bucket, Key):
            return {"Body": self}

        def read(self):
            return self.storage["objects.zip"]

        def put_object(self, Bucket, Key, Body):
            calls["put"] = (Bucket, Key, Body)

        def delete_object(self, Bucket, Key):
            calls["delete"] = (Bucket, Key)

        def head_object(self, Bucket, Key):
            if Key == "objects.zip":
                return {"ETag": '"etag-val"'}
            raise Exception("NoSuchKey")

        def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
            return "https://signed.example/put"

    class DummyBoto3:
        @staticmethod
        def client(*a, **k):
            return DummyClient()

    monkeypatch.setattr(backend, "boto3", DummyBoto3())

    s3 = backend.S3Backend(bucket="mybucket")
    data = s3.read_bytes("objects.zip")
    assert data == b"data"

    s3.write_bytes("new.zip", b"x")
    assert "put" in calls and calls["put"][1] == "new.zip"

    s3.delete_bytes("old.zip")
    assert "delete" in calls and calls["delete"][1] == "old.zip"

    assert s3.exists("objects.zip") is True
    assert s3.get_hash("objects.zip") == "etag-val"

    url = s3.generate_presigned_put("objects.zip")
    assert url.startswith("https://signed.example")
