"""Thin stdlib HTTP wrapper for running the Lambda handler locally.

Usage:
    python local_server.py [--port 8787]
"""

import argparse
import json
import logging
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from python_lib.storage import backend as storage_backend
from python_lib.storage.backend import LocalBackend

from handler import lambda_handler

logger = logging.getLogger(__name__)


class LocalLambdaHandler(BaseHTTPRequestHandler):
    """HTTP request handler that simulates Lambda Function URL events."""

    def _cors_origin(self):
        origin = self.headers.get("Origin", "")
        allowed = {
            x.strip()
            for x in os.environ.get(
                "LOCAL_CORS_ORIGINS", "http://localhost:6543,http://127.0.0.1:6543"
            ).split(",")
            if x.strip()
        }
        return origin if origin in allowed else ""

    def _build_event(self):
        """Construct a Lambda Function URL event dict from the HTTP request."""
        parsed_url = urlparse(self.path)

        # Read request body if present
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length).decode("utf-8")
        else:
            body = None

        # Parse query string
        query_params = parse_qs(parsed_url.query)
        query_string_params = None
        if query_params:
            query_string_params = {k: v[0] for k, v in query_params.items()}

        # Build Lambda event structure
        # See: https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html
        return {
            "version": "2.0",
            "routeKey": "$default",
            "rawPath": parsed_url.path,
            "rawQueryString": parsed_url.query,
            "headers": dict(self.headers),
            "queryStringParameters": query_string_params,
            "requestContext": {
                "accountId": "anonymous",
                "apiId": "local",
                "domainName": "localhost",
                "domainPrefix": "local",
                "http": {
                    "method": self.command,
                    "path": parsed_url.path,
                    "protocol": "HTTP/1.1",
                    "sourceIp": self.client_address[0],
                    "userAgent": self.headers.get("User-Agent", ""),
                },
                "requestId": "local",
                "routeKey": "$default",
                "stage": "$default",
                "time": "",
                "timeEpoch": 0,
            },
            "body": body,
            "isBase64Encoded": False,
        }

    def _send_response_from_lambda(self, lambda_response):
        """Send HTTP response from Lambda handler result."""
        status_code = lambda_response.get("statusCode", 200)
        headers = lambda_response.get("headers", {})
        body = lambda_response.get("body", "")

        self.send_response(status_code)
        cors_origin = self._cors_origin()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header(
                "Access-Control-Allow-Headers", "Authorization,Content-Type"
            )
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

        if body:
            self.wfile.write(body.encode("utf-8"))

    def _serve_local_storage(self, key: str):
        """Serve a file from the local storage backend over HTTP."""
        backend = storage_backend.get_backend()
        if not isinstance(backend, LocalBackend):
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "local-storage not available"}')
            return
        path = backend.local_file_path(key)
        if not path.exists():
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Not found: {key}"}).encode())
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        cors_origin = self._cors_origin()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header(
                "Access-Control-Allow-Headers", "Authorization,Content-Type"
            )
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.end_headers()
        with path.open("rb") as fh:
            self.wfile.write(fh.read())

    def _handle_request(self):
        """Generic request handler for all HTTP methods."""
        try:
            event = self._build_event()
            result = lambda_handler(event, context=None)
            self._send_response_from_lambda(result)
        except Exception as e:
            logger.exception("Unhandled error handling request")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            cors_origin = self._cors_origin()
            if cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header(
                    "Access-Control-Allow-Headers", "Authorization,Content-Type"
                )
                self.send_header(
                    "Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS"
                )
            self.end_headers()
            error_body = json.dumps({"error": f"Internal server error: {e!s}"})
            self.wfile.write(error_body.encode("utf-8"))

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        prefix = "/local-storage/"
        if parsed.path.startswith(prefix):
            key = parsed.path[len(prefix):]
            self._serve_local_storage(key)
            return
        self._handle_request()

    def do_POST(self):
        """Handle POST requests."""
        self._handle_request()

    def do_DELETE(self):
        """Handle DELETE requests."""
        self._handle_request()

    def do_OPTIONS(self):
        """Handle OPTIONS (CORS preflight) requests."""
        self._handle_request()

    def log_message(self, fmt, *args):
        """Override to customize log format."""
        logger.info("[local_server] %s", fmt % args)


def main():
    """Start the local development server."""
    logging.basicConfig(
        level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Local Lambda wrapper")
    parser.add_argument("--port", type=int, default=8787, help="Port to listen on")
    args = parser.parse_args()

    server = HTTPServer(("localhost", args.port), LocalLambdaHandler)
    logger.info("Local Lambda server listening on http://localhost:%d", args.port)
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.shutdown()


if __name__ == "__main__":
    main()
