"""Thin stdlib HTTP wrapper for running the Lambda handler locally.

Usage:
    python local_server.py [--port 8787]
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from handler import lambda_handler


class LocalLambdaHandler(BaseHTTPRequestHandler):
    """HTTP request handler that simulates Lambda Function URL events."""

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
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

        if body:
            self.wfile.write(body.encode("utf-8"))

    def _handle_request(self):
        """Generic request handler for all HTTP methods."""
        try:
            event = self._build_event()
            result = lambda_handler(event, context=None)
            self._send_response_from_lambda(result)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_body = json.dumps({"error": f"Internal server error: {e!s}"})
            self.wfile.write(error_body.encode("utf-8"))

    def do_GET(self):
        """Handle GET requests."""
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
        print(f"[local_server] {fmt % args}")


def main():
    """Start the local development server."""
    parser = argparse.ArgumentParser(description="Local Lambda wrapper")
    parser.add_argument("--port", type=int, default=8787, help="Port to listen on")
    args = parser.parse_args()

    server = HTTPServer(("localhost", args.port), LocalLambdaHandler)
    print(f"Local Lambda server listening on http://localhost:{args.port}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == "__main__":
    main()
