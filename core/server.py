"""
server.py — Local HTTP server for the interactive job digest.
Serves the HTML digest and handles checkbox (applied) state changes.
"""
import asyncio
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from core.db import mark_applied, get_recent_jobs
from core.user_config import load_config, save_config
from core.cv_parser import extract_pdf_text

_state = {"processing": False}


class DigestHandler(BaseHTTPRequestHandler):
    days = 30

    def do_GET(self):
        if self.path == "/":
            from core.emailer import build_html
            from core.filters import title_matches, MATCH_THRESHOLD
            config = load_config()
            rows = get_recent_jobs(days=self.days)
            title_keywords = config.get("roles", [])
            jobs = [
                dict(r) for r in rows
                if title_matches(r["title"] or "", keywords=title_keywords if title_keywords else None)
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
        elif self.path == "/settings":
            config = load_config()
            roles_text = "\n".join(config.get("roles", []))
            locations_text = "\n".join(config.get("locations", []))
            threshold = config.get("match_threshold", 0.75)
            cv_chars = len(config.get("cv_text", ""))

            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Agent Settings</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; color: #333; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        nav {{ margin-bottom: 30px; }}
        nav a {{ margin-right: 20px; text-decoration: none; color: #3498db; font-weight: 500; }}
        nav a.active {{ color: #2c3e50; border-bottom: 2px solid #3498db; }}
        section {{ margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; }}
        h2 {{ color: #2c3e50; font-size: 18px; margin-top: 0; }}
        textarea, input[type="text"], input[type="number"] {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; }}
        input[type="number"] {{ font-family: inherit; }}
        button {{ background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: 500; margin: 10px 0; }}
        button:hover {{ background: #2980b9; }}
        .hint {{ font-size: 14px; color: #666; margin-top: 8px; }}
        #cv-status, #run-status {{ margin-top: 10px; padding: 10px; border-radius: 4px; }}
        #cv-status.success {{ background: #d4edda; color: #155724; }}
        #cv-status.error {{ background: #f8d7da; color: #721c24; }}
    </style>
</head>
<body>
    <nav>
        <a href="/">📊 Job Digest</a>
        <a href="/settings" class="active">⚙ Settings</a>
    </nav>

    <h1>Job Agent Settings</h1>

    <form action="/settings" method="POST">
        <section>
            <h2>Role Keywords</h2>
            <textarea name="roles" rows="8">{roles_text}</textarea>
            <p class="hint">One role per line. Used as search queries on all platforms.</p>
        </section>

        <section>
            <h2>Locations</h2>
            <textarea name="locations" rows="5">{locations_text}</textarea>
            <p class="hint">One location per line. "Remote" is treated as a remote-only filter.</p>
        </section>

        <section>
            <h2>Match Threshold</h2>
            <input type="number" name="match_threshold" min="0" max="1" step="0.05" value="{threshold}">
            <p class="hint">Minimum match score (0.0–1.0) to show a job. Default: 0.75</p>
        </section>

        <button type="submit">💾 Save Settings</button>
    </form>

    <section>
        <h2>CV / Resume</h2>
        <form id="cv-form" enctype="multipart/form-data" style="display: contents;">
            <div style="background: white; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
                <p><strong>Upload PDF:</strong></p>
                <input type="file" id="cv_file" name="cv_file" accept=".pdf" style="margin-bottom: 15px;">
                <button type="button" onclick="uploadCV('file')" style="display: inline-block; margin-right: 10px;">📤 Upload PDF</button>
                <p class="hint" style="margin-top: 5px;">Supported: PDF files</p>
            </div>

            <div style="background: white; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
                <p><strong>Or paste plain text:</strong></p>
                <textarea name="cv_text" id="cv_text" rows="10" placeholder="Paste your CV/resume here..."></textarea>
                <button type="button" onclick="uploadCV('text')" style="display: inline-block;">📋 Upload Text</button>
                <p class="hint" style="margin-top: 5px;">Plain text CV content</p>
            </div>

            <div id="cv-status"></div>
            <p class="hint">Current CV: {cv_chars} characters</p>
        </form>
    </section>

    <section>
        <h2>Start Search</h2>
        <p>Trigger a new job search with current settings.</p>
        <button onclick="startRun()" style="background: #27ae60;">🚀 Start Search</button>
        <button onclick="clearDatabase()" style="background: #e74c3c; margin-left: 10px;">🗑️ Clear Old Jobs</button>
        <div id="run-status"></div>
    </section>

    <script>
        async function uploadCV(mode) {{
            const formData = new FormData();
            let payload = {{}};

            if (mode === 'file') {{
                const file = document.getElementById('cv_file').files[0];
                if (!file) {{
                    alert('Please select a PDF file');
                    return;
                }}
                formData.append('cv_file', file);
            }} else {{
                const text = document.getElementById('cv_text').value;
                if (!text.trim()) {{
                    alert('Please paste some CV text');
                    return;
                }}
                formData.append('cv_text', text);
            }}

            try {{
                const r = await fetch('/upload-cv', {{ method: 'POST', body: formData }});
                const data = await r.json();
                const status = document.getElementById('cv-status');
                if (data.ok) {{
                    status.textContent = '✅ CV saved (' + data.chars + ' characters)';
                    status.className = 'success';
                }} else {{
                    status.textContent = '❌ Error: ' + (data.error || 'Unknown error');
                    status.className = 'error';
                }}
            }} catch (e) {{
                document.getElementById('cv-status').textContent = '❌ Error: ' + e.message;
                document.getElementById('cv-status').className = 'error';
            }}
        }}

        async function startRun() {{
            try {{
                const r = await fetch('/run', {{ method: 'POST' }});
                const data = await r.json();
                const status = document.getElementById('run-status');
                if (data.ok) {{
                    status.innerHTML = '✅ Search started! Check the <a href="/">Job Digest</a> to see results.';
                }} else {{
                    status.textContent = '⚠️ ' + (data.error || 'Could not start search');
                }}
            }} catch (e) {{
                document.getElementById('run-status').textContent = '❌ Error: ' + e.message;
            }}
        }}

        async function clearDatabase() {{
            if (!confirm('Clear all old jobs from the database? You will only see new jobs from your next search.')) {{
                return;
            }}
            try {{
                const r = await fetch('/clear-db', {{ method: 'POST' }});
                const data = await r.json();
                const status = document.getElementById('run-status');
                if (data.ok) {{
                    status.textContent = '✅ Old jobs cleared! Next search will start fresh.';
                }} else {{
                    status.textContent = '❌ Error: ' + (data.error || 'Could not clear database');
                }}
            }} catch (e) {{
                document.getElementById('run-status').textContent = '❌ Error: ' + e.message;
            }}
        }}
    </script>
</body>
</html>"""
            body = html.encode("utf-8")
            self._respond(200, "text/html; charset=utf-8", body)
        else:
            self._respond(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/apply":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            mark_applied(data.get("id", ""), data.get("applied", True))
            self._respond(200, "application/json", b'{"ok":true}')
        elif self.path == "/settings":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)

            config = load_config()
            config["roles"] = [r.strip() for r in params.get("roles", [""])[0].split("\n") if r.strip()]
            config["locations"] = [l.strip() for l in params.get("locations", [""])[0].split("\n") if l.strip()]

            try:
                config["match_threshold"] = float(params.get("match_threshold", ["0.75"])[0])
            except (ValueError, IndexError):
                config["match_threshold"] = 0.75

            save_config(config)

            # Redirect to /settings (HTTP 303)
            self.send_response(303)
            self.send_header("Location", "/settings")
            self.end_headers()
        elif self.path == "/upload-cv":
            content_type = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            try:
                config = load_config()

                if "multipart/form-data" in content_type:
                    # Parse multipart form data
                    boundary = content_type.split("boundary=")[1].split(";")[0].encode()
                    parts = body.split(b"--" + boundary)

                    cv_text = ""
                    for part in parts:
                        if b"filename=" in part:
                            # PDF file upload
                            if b".pdf" in part.lower():
                                start = part.find(b"\r\n\r\n") + 4
                                end = part.rfind(b"\r\n")
                                pdf_bytes = part[start:end]
                                try:
                                    cv_text = extract_pdf_text(pdf_bytes)
                                except Exception as e:
                                    raise ValueError(f"PDF parse error: {e}")
                        elif b'name="cv_text"' in part:
                            # Text field
                            start = part.find(b"\r\n\r\n") + 4
                            end = part.rfind(b"\r\n")
                            cv_text = part[start:end].decode("utf-8")

                    if cv_text:
                        config["cv_text"] = cv_text
                        save_config(config)
                        response = json.dumps({"ok": True, "chars": len(cv_text)}).encode()
                    else:
                        response = json.dumps({"ok": False, "error": "No CV data found"}).encode()
                else:
                    response = json.dumps({"ok": False, "error": "Invalid content type"}).encode()

                self._respond(200, "application/json", response)
            except Exception as e:
                response = json.dumps({"ok": False, "error": str(e)}).encode()
                self._respond(400, "application/json", response)
        elif self.path == "/run":
            if _state["processing"]:
                response = json.dumps({"ok": False, "error": "Search already running"}).encode()
                self._respond(200, "application/json", response)
            else:
                # Start run in background thread
                def run_pipeline_bg():
                    from main import run_pipeline
                    config = load_config()
                    _state["processing"] = True
                    try:
                        asyncio.run(run_pipeline(config, test_mode=False))
                    except Exception as e:
                        print(f"[Error] Background run failed: {e}")
                    finally:
                        _state["processing"] = False

                t = threading.Thread(target=run_pipeline_bg, daemon=True)
                t.start()
                response = json.dumps({"ok": True}).encode()
                self._respond(200, "application/json", response)
        elif self.path == "/clear-db":
            try:
                from core.db import get_connection
                with get_connection() as conn:
                    conn.execute("DELETE FROM seen_jobs")
                    conn.commit()
                response = json.dumps({"ok": True}).encode()
                self._respond(200, "application/json", response)
            except Exception as e:
                response = json.dumps({"ok": False, "error": str(e)}).encode()
                self._respond(400, "application/json", response)
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
