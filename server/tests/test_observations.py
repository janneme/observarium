import json

from botocore.exceptions import ClientError

import handler


def make_event_with_token(token: str, body: str | None = None):
    ev = {"headers": {"Authorization": f"Bearer {token}"}}
    if body is not None:
        ev["body"] = body
    return ev


def test_get_observations_not_found(monkeypatch):
    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")

    class DummyS3:
        def get_object(self, Bucket, Key):
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    monkeypatch.setattr(handler, "_s3_client", lambda: DummyS3())
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user1"})

    ev = make_event_with_token("tok")
    res = handler.handle_get_observations(ev)
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == []


def test_save_observations_success(monkeypatch):
    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")

    saved = {}

    class DummyS3:
        def put_object(self, Bucket, Key, Body, ContentType=None):
            saved["Bucket"] = Bucket
            saved["Key"] = Key
            saved["Body"] = Body
            return {}

    monkeypatch.setattr(handler, "_s3_client", lambda: DummyS3())
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user2"})

    arr = [{"date": "2026-01-01", "note": "obs"}]
    ev = make_event_with_token("tok", body=json.dumps(arr))
    res = handler.handle_save_observations(ev)
    assert res["statusCode"] == 200
    assert saved["Bucket"] == "test-bucket"
    assert saved["Key"] == "observations/user2.json"
    assert json.loads(saved["Body"]) == arr


def test_delete_observation(monkeypatch):
    monkeypatch.setattr(handler, "DATA_BUCKET", "test-bucket")

    initial = [{"date": "2026-01-01", "x": 1}, {"date": "2026-02-01", "x": 2}]

    class DummyBody:
        def __init__(self, b):
            self._b = b

        def read(self):
            return self._b

    class DummyS3:
        def __init__(self):
            self.stored = None

        def get_object(self, Bucket, Key):
            return {"Body": DummyBody(json.dumps(initial).encode("utf-8"))}

        def put_object(self, Bucket, Key, Body, ContentType=None):
            self.stored = Body
            return {}

    s3 = DummyS3()
    monkeypatch.setattr(handler, "_s3_client", lambda: s3)
    monkeypatch.setattr(handler, "verify_jwt", lambda token: {"sub": "user3"})

    ev = make_event_with_token("tok")
    # set module global event used by delete handler
    handler_globals = globals()
    handler_globals["_CURRENT_EVENT"] = ev
    # also set handler module global so function can read
    __import__("builtins")
    # ensure handler has _CURRENT_EVENT
    handler_globals = handler.__dict__
    handler_globals["_CURRENT_EVENT"] = ev

    res = handler.handle_delete_observation("2026-01-01")
    assert res["statusCode"] == 200
    saved = json.loads(s3.stored.decode("utf-8"))
    assert saved == [{"date": "2026-02-01", "x": 2}]
