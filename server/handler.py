"""AWS Lambda entry point for the Observarium API.

Step 12: Implements `POST /login` using Cognito `initiate_auth` and provides
JWT verification helpers that fetch and cache Cognito JWKS for token checks.
"""

import json
import os
import time
from typing import Any

import boto3
import jwt
from botocore.exceptions import ClientError
from jwt import PyJWKClient

COGNITO_REGION = os.environ.get("COGNITO_REGION", "eu-central-1")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID")
DATA_BUCKET = os.environ.get("DATA_BUCKET")

# JWKS client cache: {jwks_url: (PyJWKClient, expiry_timestamp)}
_JWK_CLIENT_CACHE: dict[str, Any] = {}
BEARER_PARTS = 2


def build_response(status_code: int, body: dict | None = None):
    """Build a Lambda response with CORS headers."""
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
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
    """Verify JWT using Cognito JWKS. Returns decoded claims or raises."""
    jwk_client = _get_jwk_client()
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    # Verify audience if client id provided
    options = {"verify_aud": bool(COGNITO_CLIENT_ID)}
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=COGNITO_CLIENT_ID if COGNITO_CLIENT_ID else None,
        options=options,
    )


def _cognito_client():
    return boto3.client("cognito-idp", region_name=COGNITO_REGION)


def _s3_client():
    aws_region = os.environ.get("AWS_REGION", COGNITO_REGION)
    return boto3.client("s3", region_name=aws_region)


def _generate_presigned_put(key: str, expires: int = 300) -> str:
    """Generate a presigned PUT URL for `key` in the data bucket."""
    if not DATA_BUCKET:
        raise RuntimeError("DATA_BUCKET not set in environment")
    client = _s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": DATA_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def handle_presign_key(key: str) -> dict:
    """Return a dict containing a presigned PUT URL and metadata for `key`."""
    url = _generate_presigned_put(key)
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
    client = _s3_client()
    out: dict = {}
    for name, key in keys.items():
        try:
            head = client.head_object(Bucket=DATA_BUCKET, Key=key)
            etag = head.get("ETag")
            # ETag may be quoted; strip quotes
            if etag and etag.startswith('"') and etag.endswith('"'):
                etag = etag[1:-1]
            out[name] = etag
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NotFound", "NoSuchKey"):
                out[name] = None
            else:
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
        # Do not reveal whether user exists
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            return build_response(401, {"error": "Invalid username or password"})
        return build_response(500, {"error": "Authentication failed"})
    except Exception:
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


def _route_preflight(method: str):
    if method == "OPTIONS":
        return build_response(200)
    return None


def _route_health(path: str, method: str):
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
            return build_response(401, {"error": "Invalid token"})
        try:
            out = handle_presign_key("objects.zip")
            return build_response(200, out)
        except Exception:
            return build_response(500, {"error": "Could not generate presigned URL"})

    if path == "/images-url":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            verify_jwt(token)
        except Exception:
            return build_response(401, {"error": "Invalid token"})
        try:
            out = handle_presign_key("images.zip")
            return build_response(200, out)
        except Exception:
            return build_response(500, {"error": "Could not generate presigned URL"})

    return None


def _route_data_hash(path: str, method: str):
    if path == "/data-hash" and method == "GET":
        try:
            out = handle_data_hash()
            return build_response(200, out)
        except Exception:
            return build_response(500, {"error": "Could not fetch data hashes"})
    return None


def _route_observations(path: str, method: str):
    if path == "/observations" and method == "GET":
        return build_response(501, {"error": "Get observations not yet implemented"})
    if path == "/observations" and method == "POST":
        return build_response(501, {"error": "Save observations not yet implemented"})
    if path.startswith("/observations/") and method == "DELETE":
        return build_response(501, {"error": "Delete observation not yet implemented"})
    return None


def lambda_handler(event, context):  # pylint: disable=unused-argument
    """Handle Lambda invocations by delegating to smaller route functions."""
    path = event.get("rawPath", "/")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

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
        if fn in (_route_login, _route_presign):
            resp = fn(path, method, event)
        else:
            resp = fn(path, method)

        if resp is not None:
            return resp

    return build_response(404, {"error": f"Not found: {method} {path}"})
