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


def lambda_handler(event, context):  # pylint: disable=unused-argument
    """Handle Lambda invocations.

    Routes requests based on rawPath and HTTP method.
    """
    # Extract request details
    path = event.get("rawPath", "/")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    # Handle CORS preflight
    if method == "OPTIONS":
        return build_response(200)

    # Health check endpoint
    if path == "/" and method == "GET":
        return build_response(200, {"status": "ok"})

    # Authentication
    if path == "/login" and method == "POST":
        return handle_login(event)

    # Protected endpoints example (will require JWT verification in later steps)
    if path == "/objects-url" and method == "GET":
        token = _get_bearer_token_from_event(event)
        if not token:
            return build_response(401, {"error": "Authorization required"})
        try:
            claims = verify_jwt(token)
        except Exception:
            return build_response(401, {"error": "Invalid token"})

        return build_response(
            501,
            {
                "error": "Objects URL not yet implemented",
                "sub": claims.get("sub"),
            },
        )

    if path == "/images-url" and method == "GET":
        return build_response(501, {"error": "Images URL not yet implemented"})

    if path == "/data-hash" and method == "GET":
        return build_response(501, {"error": "Data hash not yet implemented"})

    if path == "/observations" and method == "GET":
        return build_response(501, {"error": "Get observations not yet implemented"})

    if path == "/observations" and method == "POST":
        return build_response(501, {"error": "Save observations not yet implemented"})

    if path.startswith("/observations/") and method == "DELETE":
        return build_response(501, {"error": "Delete observation not yet implemented"})

    # Not found
    return build_response(404, {"error": f"Not found: {method} {path}"})
