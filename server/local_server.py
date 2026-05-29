"""Thin stdlib HTTP wrapper for running the Lambda handler locally.

Usage:
    python local_server.py [--port 8080]
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from handler import lambda_handler


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        event = json.loads(body) if body else {}
        result = lambda_handler(event, context=None)
        payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):  # pylint: disable=arguments-differ
        print(f"[local_server] {fmt % args}")


def main():
    parser = argparse.ArgumentParser(description="Local Lambda wrapper")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = HTTPServer(("localhost", args.port), _Handler)
    print(f"Listening on http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
