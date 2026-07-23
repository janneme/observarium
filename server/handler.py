"""AWS Lambda entry point for the Observarium API.

Step 12: Implements `POST /login` using Cognito `initiate_auth` and provides
JWT verification helpers that fetch and cache Cognito JWKS for token checks.
"""

import json
import logging
import os
import time
import traceback
from typing import Any

import boto3
import jwt
from botocore.exceptions import ClientError
from jwt import PyJWKClient
from python_lib.storage import backend as storage_backend

logger = logging.getLogger(__name__)

COGNITO_REGION = os.environ.get("COGNITO_REGION", "eu-central-1")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID")
DATA_BUCKET = os.environ.get("DATA_BUCKET")

# JWKS client cache: {jwks_url: (PyJWKClient, expiry_timestamp)}
_JWK_CLIENT_CACHE: dict[str, Any] = {}
BEARER_PARTS = 2


def build_response(status_code: int, body: dict | list | None = None):
    """Build a JSON API response dict.

    CORS headers are provided by the Lambda Function URL configuration in
    production and by local_server.py in local development.
    """
    headers = {
        "Content-Type": "application/json",
    }

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body) if body is not None else "",
    }


def _get_jwks_url() -> str:
    if not COGNITO_USER_POOL_ID:
        raise RuntimeError("COGNITO_USER_POOL_ID not set in environment")
    return (
        "https://cognito-idp."
        f"{COGNITO_REGION}.amazonaws.com/"
        f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    )


def _get_jwk_client() -> PyJWKClient:
    """Return a cached PyJWKClient for the Cognito JWKS URL (with simple expiry)."""
    jwks_url = _get_jwks_url()
    entry = _JWK_CLIENT_CACHE.get(jwks_url)
    now = time.time()
    if entry and entry[1] > now:
        return entry[0]

    # Create new client and cache for 10 minutes
    client = PyJWKClient(jwks_url)
    _JWK_CLIENT_CACHE[jwks_url] = (client, now + 600)
    return client


def verify_jwt(token: str) -> dict:
    """Verify JWT using Cognito JWKS. Returns decoded claims or raises.

    Cognito access tokens carry 'client_id' not 'aud', so audience
    verification is skipped; signature verification against the pool's
    JWKS is sufficient.
    """
    jwk_client = _get_jwk_client()
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    if COGNITO_CLIENT_ID and claims.get("client_id") != COGNITO_CLIENT_ID:
        raise ValueError("Token client_id does not match expected client")
    return claims


def _cognito_client():
    return boto3.client("cognito-idp", region_name=COGNITO_REGION)


def _s3_client():
    aws_region = os.environ.get("AWS_REGION", COGNITO_REGION)
    return boto3.client("s3", region_name=aws_region)


def _generate_presigned_get(key: str, expires: int = 300) -> str:
    """Generate a presigned GET URL for `key` in the data bucket."""
    backend = storage_backend.get_backend()
    return backend.generate_presigned_get(key, expires)


def handle_presign_key(key: str) -> dict:
    """Return a dict containing a presigned GET URL and metadata for `key`."""
    url = _generate_presigned_get(key)
    return {
        "url": url,
        "bucket": DATA_BUCKET,
        "key": key,
        "expires_in": 300,
    }


def handle_data_hash() -> dict:
    """Return SHA-256 of manifest.json from data bucket."""
    backend = storage_backend.get_backend()
    try:
        manifest_hash = backend.read_bytes("manifest.hash").decode("utf-8").strip()
        return {"hash": manifest_hash}
    except Exception:
        return {"hash": None}


def handle_images_hash() -> dict:
    """Return content hash of images.zip from storage backend."""
    backend = storage_backend.get_backend()
    try:
        return {"hash": backend.get_hash("images.zip")}
    except Exception:
        return {"hash": None}


def handle_manifest(mag: int | None = None) -> dict:
    """Read manifest.json; inject presigned URLs for `mag` set when mag is given."""
    backend = storage_backend.get_backend()
    manifest = json.loads(backend.read_bytes("manifest.json"))
    if mag is not None:
        for s in manifest.get("sets", []):
            if s.get("mag") == mag:
                s["stars_t1"]["url"] = backend.generate_presigned_get(
                    s["stars_t1"]["filename"]
                )
                s["objects"]["url"] = backend.generate_presigned_get(
                    s["objects"]["filename"]
                )
                for chunk in s.get("t2_chunks", []):
                    chunk["url"] = backend.generate_presigned_get(chunk["filename"])
                break
    return manifest


def handle_login(event: dict) -> dict:
    """Handle POST /login by calling Cognito `initiate_auth`.

    Expects JSON body with `username` and `password`.
    Returns `access_token` and `expires_in` on success.
    """
    try:
        body = event.get("body") or ""
        data = (json.loads(body) if body else {}) if isinstance(body, str) else body

        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return build_response(400, {"error": "username and password required"})

        client = _cognito_client()
        resp = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
            ClientId=COGNITO_CLIENT_ID,
        )

        auth_result = resp.get("AuthenticationResult", {})
        access_token = auth_result.get("AccessToken") or auth_result.get("access_token")
        expires_in = auth_result.get("ExpiresIn") or auth_result.get("expires_in")
        if not access_token:
            return build_response(500, {"error": "Authentication did not return token"})

        return build_response(
            200,
            {
                "access_token": access_token,
                "expires_in": expires_in,
            },
        )

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            return build_response(401, {"error": "Invalid username or password"})
        traceback.print_exc()
        return build_response(500, {"error": "Authentication failed"})
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Authentication failed"})


def _get_bearer_token_from_event(event: dict) -> str | None:
    headers = event.get("headers") or {}
    # Header keys may be in any case
    auth = None
    for k, v in headers.items():
        if k.lower() == "authorization":
            auth = v
            break
    if not auth:
        return None
    parts = auth.split()
    if len(parts) == BEARER_PARTS and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _get_username_from_event(event: dict) -> str:
    token = _get_bearer_token_from_event(event)
    if not token:
        raise PermissionError("Authorization required")
    try:
        claims = verify_jwt(token)
    except Exception as exc:
        raise PermissionError("Invalid token") from exc
    sub = claims.get("sub")
    if not sub:
        raise PermissionError("Invalid token: missing sub")
    return sub


def _observations_key_for_user(username: str) -> str:
    return f"observations/{username}.json"


def _read_json_or_default(backend, key: str, default):
    """Read+parse `key` from `backend`, or return `default` if it doesn't exist."""
    if not backend.exists(key):
        return default
    data = backend.read_bytes(key)
    raw = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
    return json.loads(raw)


def _updated_at(record: dict) -> str:
    return record.get("updatedAt") or "1970-01-01T00:00:00.000Z"


def _parse_merge_body(event: dict) -> tuple[list, list] | None:
    """Parse a `{upserts: [...], deletes: [...]}` merge request body.

    Returns (upserts, deletes) or None if the body is malformed.
    """
    body = event.get("body") or ""
    try:
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    upserts = data.get("upserts")
    deletes = data.get("deletes")
    if not isinstance(upserts, list) or not isinstance(deletes, list):
        return None
    return upserts, deletes


def _merge_flat_list(
    current: list, id_field: str, upserts: list, deletes: list
) -> list:
    """Apply a delta to a flat array of records keyed by `id_field`.

    Deletes always win (even against a newer server-side record); upserts
    only replace an existing record when their `updatedAt` is at least as
    new (newest wins, ties go to the incoming client).
    """
    by_key = {item.get(id_field): item for item in current if isinstance(item, dict)}
    delete_set = {str(d) for d in deletes}
    for d in delete_set:
        by_key.pop(d, None)
    for item in upserts:
        if not isinstance(item, dict):
            continue
        k = item.get(id_field)
        if k is None or str(k) in delete_set:
            continue
        existing = by_key.get(k)
        if existing is None or _updated_at(item) >= _updated_at(existing):
            by_key[k] = item
    return list(by_key.values())


def handle_get_observations(event: dict) -> dict:
    """Return the stored observations list for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    key = _observations_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        if not backend.exists(key):
            return build_response(200, [])
        data = backend.read_bytes(key)
        raw = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        arr = json.loads(raw)
        return build_response(200, arr)
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not read observations"})


def handle_save_observations(event: dict) -> dict:
    """Persist the full observations array for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    body = event.get("body") or ""
    try:
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return build_response(400, {"error": "Invalid JSON body"})

    if not isinstance(data, list):
        return build_response(400, {"error": "Observations must be a JSON array"})

    key = _observations_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        backend.write_bytes(key, json.dumps(data).encode("utf-8"))
        return build_response(200, {"ok": True})
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not save observations"})


def handle_delete_observation(event: dict, date: str) -> dict:
    """Remove the observation with the given date for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    key = _observations_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        if not backend.exists(key):
            return build_response(404, {"error": "Not found"})
        data = backend.read_bytes(key)
        raw = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        arr = json.loads(raw)
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not read observations"})

    # Filter out entries with matching date
    new_arr = [item for item in arr if item.get("date") != date]
    try:
        backend.write_bytes(key, json.dumps(new_arr).encode("utf-8"))
        return build_response(200, {"ok": True})
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not save observations"})


def handle_merge_observations(event: dict) -> dict:
    """Apply a {upserts, deletes} delta to the stored observations array.

    Deletes always win, even against a concurrently modified server copy;
    upserts only replace an existing record when at least as new
    (`updatedAt`). Returns the full resulting array, which the client
    replaces its local copy with.
    """
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    parsed = _parse_merge_body(event)
    if parsed is None:
        return build_response(
            400, {"error": "Body must be {upserts: [...], deletes: [...]}"}
        )
    upserts, deletes = parsed

    key = _observations_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        current = _read_json_or_default(backend, key, [])
        merged = _merge_flat_list(current, "date", upserts, deletes)
        backend.write_bytes(key, json.dumps(merged).encode("utf-8"))
        return build_response(200, merged)
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not merge observations"})


def _route_preflight(_path: str, method: str, _event: dict):
    if method == "OPTIONS":
        return build_response(200)
    return None


def _route_health(path: str, method: str, _event: dict):
    if path == "/" and method == "GET":
        return build_response(200, {"status": "ok"})
    return None


def _route_login(path: str, method: str, event: dict):
    if path == "/login" and method == "POST":
        return handle_login(event)
    return None


def _route_presign(path: str, method: str, event: dict):
    if method != "GET":
        return None

    if path == "/images-url":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            verify_jwt(token)
        except Exception as exc:
            logger.warning("[auth] token rejected: %s", exc)
            return build_response(401, {"error": "Invalid token"})
        try:
            out = handle_presign_key("images.zip")
            return build_response(200, out)
        except Exception:
            traceback.print_exc()
            return build_response(500, {"error": "Could not generate presigned URL"})

    if path == "/images-hash":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            verify_jwt(token)
        except Exception as exc:
            logger.warning("[auth] token rejected: %s", exc)
            return build_response(401, {"error": "Invalid token"})
        try:
            out = handle_images_hash()
            return build_response(200, out)
        except Exception:
            traceback.print_exc()
            return build_response(500, {"error": "Could not fetch images hash"})

    return None


def _route_manifest(path: str, method: str, event: dict):
    if path == "/manifest" and method == "GET":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            verify_jwt(token)
        except Exception as exc:
            logger.warning("[auth] token rejected: %s", exc)
            return build_response(401, {"error": "Invalid token"})
        try:
            params = event.get("queryStringParameters") or {}
            mag_str = params.get("mag")
            mag = int(mag_str) if mag_str is not None else None
            out = handle_manifest(mag=mag)
            return build_response(200, out)
        except Exception:
            traceback.print_exc()
            return build_response(500, {"error": "Could not generate manifest"})
    return None


def _route_data_hash(path: str, method: str, _event: dict):
    if path == "/data-hash" and method == "GET":
        try:
            out = handle_data_hash()
            return build_response(200, out)
        except Exception:
            return build_response(500, {"error": "Could not fetch data hashes"})
    return None


def _finding_paths_key_for_user(username: str) -> str:
    return f"finding-paths/{username}.json"


def handle_get_finding_paths(event: dict) -> dict:
    """Return the stored finding paths for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    key = _finding_paths_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        if not backend.exists(key):
            return build_response(200, {})
        data = backend.read_bytes(key)
        raw = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        return build_response(200, json.loads(raw))
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not read finding paths"})


def handle_save_finding_paths(event: dict) -> dict:
    """Persist the finding paths object for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    body = event.get("body") or ""
    try:
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return build_response(400, {"error": "Invalid JSON body"})

    if not isinstance(data, dict):
        return build_response(400, {"error": "Finding paths must be a JSON object"})

    key = _finding_paths_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        backend.write_bytes(key, json.dumps(data).encode("utf-8"))
        return build_response(200, {"ok": True})
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not save finding paths"})


def handle_merge_finding_paths(event: dict) -> dict:
    """Apply a {upserts, deletes} delta to the stored finding-paths object.

    Upserts are flat `{objectId, startHip, steps, updatedAt}` records (the
    nested `{objectId: {startHip: {...}}}` storage shape is reconstructed
    here); deletes are flat `"objectId::startHip"` keys. Same delete-always-
    wins / newest-upsert-wins semantics as `_merge_flat_list`.
    """
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    parsed = _parse_merge_body(event)
    if parsed is None:
        return build_response(
            400, {"error": "Body must be {upserts: [...], deletes: [...]}"}
        )
    upserts, deletes = parsed

    key = _finding_paths_key_for_user(username)
    try:
        backend = storage_backend.get_backend()
        current = _read_json_or_default(backend, key, {})
        if not isinstance(current, dict):
            current = {}

        delete_set = {str(d) for d in deletes}
        _apply_finding_path_deletes(current, delete_set)
        _apply_finding_path_upserts(current, upserts, delete_set)

        backend.write_bytes(key, json.dumps(current).encode("utf-8"))
        return build_response(200, current)
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not merge finding paths"})


def _apply_finding_path_deletes(current: dict, delete_set: set) -> None:
    for d in delete_set:
        if "::" not in d:
            continue
        object_id, start_hip = d.split("::", 1)
        by_start = current.get(object_id)
        if isinstance(by_start, dict) and start_hip in by_start:
            del by_start[start_hip]
            if not by_start:
                del current[object_id]


def _apply_finding_path_upserts(current: dict, upserts: list, delete_set: set) -> None:
    for item in upserts:
        if not isinstance(item, dict):
            continue
        object_id = item.get("objectId")
        start_hip = item.get("startHip")
        if object_id is None or start_hip is None:
            continue
        start_hip = str(start_hip)
        if f"{object_id}::{start_hip}" in delete_set:
            continue
        record = {"steps": item.get("steps") or [], "updatedAt": item.get("updatedAt")}
        by_start = current.setdefault(object_id, {})
        existing = by_start.get(start_hip)
        if existing is None or _updated_at(record) >= _updated_at(existing):
            by_start[start_hip] = record


def _route_finding_paths(path: str, method: str, event: dict):
    if path == "/finding-paths" and method == "GET":
        return handle_get_finding_paths(event)
    if path == "/finding-paths" and method == "POST":
        return handle_save_finding_paths(event)
    if path == "/finding-paths/merge" and method == "POST":
        return handle_merge_finding_paths(event)
    return None


def _telescopes_key_for_user(username: str) -> str:
    return f"telescopes/{username}.json"


def _eyepieces_key_for_user(username: str) -> str:
    return f"eyepieces/{username}.json"


def _handle_get_flat_list(event: dict, key_fn) -> dict:
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})
    key = key_fn(username)
    try:
        backend = storage_backend.get_backend()
        return build_response(200, _read_json_or_default(backend, key, []))
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": "Could not read data"})


def _handle_save_flat_list(event: dict, key_fn, label: str) -> dict:
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})
    body = event.get("body") or ""
    try:
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return build_response(400, {"error": "Invalid JSON body"})
    if not isinstance(data, list):
        return build_response(400, {"error": f"{label} must be a JSON array"})
    key = key_fn(username)
    try:
        backend = storage_backend.get_backend()
        backend.write_bytes(key, json.dumps(data).encode("utf-8"))
        return build_response(200, {"ok": True})
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": f"Could not save {label.lower()}"})


def _handle_merge_flat_list(event: dict, key_fn, id_field: str, label: str) -> dict:
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})
    parsed = _parse_merge_body(event)
    if parsed is None:
        return build_response(
            400, {"error": "Body must be {upserts: [...], deletes: [...]}"}
        )
    upserts, deletes = parsed
    key = key_fn(username)
    try:
        backend = storage_backend.get_backend()
        current = _read_json_or_default(backend, key, [])
        merged = _merge_flat_list(current, id_field, upserts, deletes)
        backend.write_bytes(key, json.dumps(merged).encode("utf-8"))
        return build_response(200, merged)
    except Exception:
        traceback.print_exc()
        return build_response(500, {"error": f"Could not merge {label.lower()}"})


def _route_telescopes(path: str, method: str, event: dict):
    if path == "/telescopes" and method == "GET":
        return _handle_get_flat_list(event, _telescopes_key_for_user)
    if path == "/telescopes" and method == "POST":
        return _handle_save_flat_list(event, _telescopes_key_for_user, "Telescopes")
    if path == "/telescopes/merge" and method == "POST":
        return _handle_merge_flat_list(
            event, _telescopes_key_for_user, "id", "Telescopes"
        )
    return None


def _route_eyepieces(path: str, method: str, event: dict):
    if path == "/eyepieces" and method == "GET":
        return _handle_get_flat_list(event, _eyepieces_key_for_user)
    if path == "/eyepieces" and method == "POST":
        return _handle_save_flat_list(event, _eyepieces_key_for_user, "Eyepieces")
    if path == "/eyepieces/merge" and method == "POST":
        return _handle_merge_flat_list(
            event, _eyepieces_key_for_user, "id", "Eyepieces"
        )
    return None


def _lists_key_for_user(username: str) -> str:
    return f"lists/{username}.json"


def _route_lists(path: str, method: str, event: dict):
    if path == "/lists" and method == "GET":
        return _handle_get_flat_list(event, _lists_key_for_user)
    if path == "/lists" and method == "POST":
        return _handle_save_flat_list(event, _lists_key_for_user, "Lists")
    if path == "/lists/merge" and method == "POST":
        return _handle_merge_flat_list(event, _lists_key_for_user, "id", "Lists")
    return None


def _route_observations(path: str, method: str, event: dict):
    if path == "/observations" and method == "GET":
        return handle_get_observations(event)
    if path == "/observations" and method == "POST":
        return handle_save_observations(event)
    if path == "/observations/merge" and method == "POST":
        return handle_merge_observations(event)
    if path.startswith("/observations/") and method == "DELETE":
        date = path.removeprefix("/observations/")
        return handle_delete_observation(event, date)
    return None


def lambda_handler(event, context):  # pylint: disable=unused-argument
    """Handle Lambda invocations by delegating to smaller route functions."""
    path = event.get("rawPath", "/")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    # Expose the current event to handlers that need header/context access
    globals()["_CURRENT_EVENT"] = event

    # Check preflight and health quickly
    route_funcs = (
        _route_preflight,
        _route_health,
        _route_login,
        _route_presign,
        _route_manifest,
        _route_data_hash,
        _route_observations,
        _route_finding_paths,
        _route_telescopes,
        _route_eyepieces,
        _route_lists,
    )

    for fn in route_funcs:
        resp = fn(path, method, event)

        if resp is not None:
            return resp

    return build_response(404, {"error": f"Not found: {method} {path}"})
