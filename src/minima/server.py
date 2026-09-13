"""Dev server. Stdlib only — no pip install at 3am.

Serves web/ and exposes the engine over a couple of JSON endpoints.
Run it with:  python3 -m minima.server
"""

import json
import os
import pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

WEB_ROOT = pathlib.Path(__file__).resolve().parents[2] / "web"
PORT = 8765


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api()
        # "/" is the entrance, not the portfolio page. Routed here rather than
        # by renaming files: index.html is referenced by every page's rail, by
        # the demo walk, and by fifteen call sites in the UI harness, and none
        # of that is worth churning to move a front door.
        if self.path in ("/", "/index"):
            self.path = "/home.html"
        return super().do_GET()

    def do_POST(self):
        """Portfolio Mode posts holdings.

        A portfolio is a document listing everything somebody owns. It has no
        business in a query string, where it would land in server logs and
        browser history, so it travels in a body and this is the method that
        reads one.
        """
        if not self.path.startswith("/api/"):
            return self.send_error(405, "POST is for the API")
        return self._api(self._read_body())

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            # A malformed body is the caller's problem, not a stack trace: the
            # endpoint falls back to its default portfolio and says nothing was
            # read, which is better than a 500 on the first screen of a demo.
            return {}

    def _api(self, body=None):
        from . import api

        try:
            payload = api.handle(self.path, body or {})
        except api.NotFound:
            return self.send_error(404, "no such endpoint")
        except Exception as exc:  # surface it in the browser, not just the log
            # api.handle already tries the recorded golden path before it lets
            # anything escape, so getting here means we have no cached answer
            # either. still a 200 — the frontend can render an error, it can't
            # render a stack trace.
            payload = {"error": str(exc), "cached": False}

        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # we're iterating fast; never let safari cache the page
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        # quieten the static-file chatter, keep anything about /api and any
        # error. args[0] is an int on send_error paths, hence the str().
        first = str(args[0]) if args else ""
        if "/api/" in first or not first.startswith("GET /"):
            super().log_message(fmt, *args)


def serve():
    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"minima dev server -> http://localhost:{PORT}")
        if os.environ.get("MINIMA_DEMO", "").strip().lower() in ("1", "true", "yes", "on"):
            print("MINIMA_DEMO is on — every /api/ response comes off disk")
        httpd.serve_forever()


if __name__ == "__main__":
    serve()
