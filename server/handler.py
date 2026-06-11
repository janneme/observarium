"""AWS Lambda entry point for the Observarium API.

Step 12: Implements `POST /login` using Cognito `initiate_auth` and provides
JWT verification helpers that fetch and cache Cognito JWKS for token checks.
"""

import json
import os
import time
import traceback
from typing import Any

import boto3
import jwt
from botocore.exceptions import ClientError
from jwt import PyJWKClient
from python_lib.storage import backend as storage_backend

COGNITO_REGION = os.environ.get("COGNITO_REGION", "eu-central-1")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID")
DATA_BUCKET = os.environ.get("DATA_BUCKET")

# JWKS client cache: {jwks_url: (PyJWKClient, expiry_timestamp)}
_JWK_CLIENT_CACHE: dict[str, Any] = {}
BEARER_PARTS = 2


def build_response(status_code: int, body: dict | list | None = None):
    """Build a Lambda response dict. CORS headers are added by the caller environment
    (Lambda Function URL config in production, local_server.py in development)."""
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
    """Return ETag information for objects.zip and images.zip in data bucket.

    If an object is missing, its value will be null.
    """
    keys = {"objects": "objects.zip", "images": "images.zip"}
    backend = storage_backend.get_backend()
    out: dict = {}
    for name, key in keys.items():
        try:
            out[name] = backend.get_hash(key)
        except Exception:
            out[name] = None
    return out


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
            return build_response(
                500, {"error": "Authentication did not return token"}
            )

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
    claims = verify_jwt(token)
    sub = claims.get("sub")
    if not sub:
        raise PermissionError("Invalid token: missing sub")
    return sub


def _observations_key_for_user(username: str) -> str:
    return f"observations/{username}.json"


def handle_get_observations(event: dict) -> dict:
    """Return the stored observations list for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    backend = storage_backend.get_backend()
    key = _observations_key_for_user(username)
    try:
        if not backend.exists(key):
            return build_response(200, [])
        data = backend.read_bytes(key)
        raw = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        arr = json.loads(raw)
        return build_response(200, arr)
    except Exception:
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

    backend = storage_backend.get_backend()
    key = _observations_key_for_user(username)
    try:
        backend.write_bytes(key, json.dumps(data).encode("utf-8"))
        return build_response(200, {"ok": True})
    except Exception:
        return build_response(500, {"error": "Could not save observations"})


def handle_delete_observation(event: dict, date: str) -> dict:
    """Remove the observation with the given date for the authenticated user."""
    try:
        username = _get_username_from_event(event)
    except PermissionError:
        return build_response(401, {"error": "Authorization required"})

    backend = storage_backend.get_backend()
    key = _observations_key_for_user(username)
    try:
        if not backend.exists(key):
            return build_response(404, {"error": "Not found"})
        data = backend.read_bytes(key)
        raw = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        arr = json.loads(raw)
    except Exception:
        return build_response(500, {"error": "Could not read observations"})

    # Filter out entries with matching date
    new_arr = [item for item in arr if item.get("date") != date]
    try:
        backend.write_bytes(key, json.dumps(new_arr).encode("utf-8"))
        return build_response(200, {"ok": True})
    except Exception:
        return build_response(500, {"error": "Could not save observations"})


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

    if path == "/objects-url":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            verify_jwt(token)
        except Exception:
            traceback.print_exc()
            return build_response(401, {"error": "Invalid token"})
        try:
            out = handle_presign_key("objects.zip")
            return build_response(200, out)
        except Exception:
            traceback.print_exc()
            return build_response(500, {"error": "Could not generate presigned URL"})

    if path == "/images-url":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            verify_jwt(token)
        except Exception:
            traceback.print_exc()
            return build_response(401, {"error": "Invalid token"})
        try:
            out = handle_presign_key("images.zip")
            return build_response(200, out)
        except Exception:
            traceback.print_exc()
            return build_response(500, {"error": "Could not generate presigned URL"})

    return None


def _route_data_hash(path: str, method: str, _event: dict):
    if path == "/data-hash" and method == "GET":
        try:
            out = handle_data_hash()
            return build_response(200, out)
        except Exception:
            return build_response(500, {"error": "Could not fetch data hashes"})
    return None


def _route_observations(path: str, method: str, event: dict):
    if path == "/observations" and method == "GET":
        return handle_get_observations(event)
    if path == "/observations" and method == "POST":
        return handle_save_observations(event)
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
        _route_data_hash,
        _route_observations,
    )

    for fn in route_funcs:
        resp = fn(path, method, event)

        if resp is not None:
            return resp

    return build_response(404, {"error": f"Not found: {method} {path}"})
