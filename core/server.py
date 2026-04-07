"""
server.py — Local HTTP server for the interactive job digest.
Serves the HTML digest and handles checkbox (applied) state changes.
"""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.db import mark_applied, get_recent_jobs

_state = {"processing": False}


class DigestHandler(BaseHTTPRequestHandler):
    days = 30

    def do_GET(self):
        if self.path == "/":
            from core.emailer import build_html
            from core.filters import title_matches, MATCH_THRESHOLD
            rows = get_recent_jobs(days=self.days)
            jobs = [
                dict(r) for r in rows
                if title_matches(r["title"] or "")
                and (r["match_score"] or 0) >= MATCH_THRESHOLD
            ]
            body = build_html(jobs).encode("utf-8")
            self._respond(200, "text/html; charset=utf-8", body)
        elif self.path == "/status":
            rows = get_recent_jobs(days=self.days)
            # Count includes all saved jobs so page reloads when any new job arrives
            body = json.dumps({
                "processing": _state["processing"],
                "count": len(rows),
            }).encode()
            self._respond(200, "application/json", body)
        else:
            self._respond(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/apply":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            mark_applied(data.get("id", ""), data.get("applied", True))
            self._respond(200, "application/json", b'{"ok":true}')
        else:
            self._respond(404, "text/plain", b"Not found")

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # suppress request logs


def _make_server(days, port):
    DigestHandler.days = days
    return HTTPServer(("localhost", port), DigestHandler)


def start_server_thread(days: int = 30, port: int = 8765):
    """Start server in background daemon thread, open browser. Returns httpd."""
    _state["processing"] = True
    httpd = _make_server(days, port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f"http://localhost:{port}"
    print(f"[Digest] Live at {url}")
    webbrowser.open(url)
    return httpd


def set_done():
    _state["processing"] = False


def serve_digest(days: int = 30, port: int = 8765):
    """Blocking mode for --from-db. Ctrl+C to stop."""
    _state["processing"] = False
    httpd = _make_server(days, port)
    url = f"http://localhost:{port}"
    print(f"[Digest] Serving at {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
