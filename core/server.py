"""
server.py — Local HTTP server for the interactive job digest.
Serves the HTML digest and handles checkbox (applied) state changes.
User preferences are now managed via browser localStorage only.
"""
import asyncio
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from core.db import mark_applied, get_recent_jobs
from core.cv_parser import extract_pdf_text

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
                if (r["match_score"] or 0) >= MATCH_THRESHOLD
            ]
            body = build_html(jobs).encode("utf-8")
            self._respond(200, "text/html; charset=utf-8", body)
        elif self.path == "/status":
            rows = get_recent_jobs(days=self.days)
            body = json.dumps({
                "processing": _state["processing"],
                "count": len(rows),
            }).encode()
            self._respond(200, "application/json", body)
        elif self.path == "/settings":
            html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Agent Settings</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; color: #333; }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        nav { margin-bottom: 30px; }
        nav a { margin-right: 20px; text-decoration: none; color: #3498db; font-weight: 500; }
        nav a.active { color: #2c3e50; border-bottom: 2px solid #3498db; }
        section { margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; }
        h2 { color: #2c3e50; font-size: 18px; margin-top: 0; }
        textarea, input[type="text"], input[type="number"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; box-sizing: border-box; }
        input[type="number"] { font-family: inherit; }
        .checkbox-group { margin: 10px 0; }
        .checkbox-group label { display: block; margin: 8px 0; }
        .checkbox-group input[type="checkbox"] { margin-right: 8px; }
        button { background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: 500; margin: 10px 0; margin-right: 10px; }
        button:hover { background: #2980b9; }
        .hint { font-size: 14px; color: #666; margin-top: 8px; }
        #status { margin-top: 10px; padding: 10px; border-radius: 4px; display: none; }
        #status.success { background: #d4edda; color: #155724; display: block; }
        #status.error { background: #f8d7da; color: #721c24; display: block; }
    </style>
</head>
<body>
    <nav>
        <a href="/">📊 Job Digest</a>
        <a href="/settings" class="active">⚙ Settings</a>
    </nav>

    <h1>Job Agent Settings</h1>

    <section>
        <h2>Role Keywords</h2>
        <textarea id="roles" rows="8" placeholder="Data Scientist&#10;Data Analyst&#10;Analytics Engineer"></textarea>
        <p class="hint">One role per line. Used as search queries on all platforms.</p>
    </section>

    <section>
        <h2>Locations</h2>
        <textarea id="locations" rows="5" placeholder="Germany&#10;Netherlands&#10;Remote"></textarea>
        <p class="hint">One location per line.</p>
    </section>

    <section>
        <h2>Match Threshold</h2>
        <input type="number" id="match_threshold" min="0" max="1" step="0.05" value="0.75">
        <p class="hint">Minimum match score (0.0–1.0) to show a job. Default: 0.75</p>
    </section>

    <section>
        <h2>Job Boards</h2>
        <p class="hint">Select which job boards to search:</p>
        <div class="checkbox-group">
            <label><input type="checkbox" id="scraper_linkedin" checked> LinkedIn</label>
            <label><input type="checkbox" id="scraper_stepstone" checked> Stepstone</label>
            <label><input type="checkbox" id="scraper_xing" checked> Xing</label>
        </div>
    </section>

    <section>
        <h2>CV / Resume</h2>
        <p><strong>Upload PDF:</strong></p>
        <input type="file" id="cv_file" accept=".pdf" style="margin-bottom: 15px;">
        <button onclick="uploadCV('file')">📤 Upload PDF</button>
        <p class="hint" style="margin-top: 5px;">Supported: PDF files</p>

        <p style="margin-top: 20px;"><strong>Or paste plain text:</strong></p>
        <textarea id="cv_text" rows="10" placeholder="Paste your CV/resume here..."></textarea>
        <button onclick="uploadCV('text')">📋 Upload Text</button>
        <p class="hint" style="margin-top: 5px;">Plain text CV content</p>

        <div id="status"></div>
        <button onclick="showCurrentCV()" style="background: #6366f1;">👁️ Preview CV</button>
        <button onclick="clearCV()" style="background: #ef4444;">❌ Clear CV</button>
        <div id="cv-preview" style="margin-top: 15px; padding: 10px; background: #f3f4f6; border-radius: 4px; max-height: 200px; overflow-y: auto; display: none; white-space: pre-wrap; font-family: monospace; font-size: 12px;"></div>
    </section>

    <section>
        <h2>Actions</h2>
        <button onclick="saveSettings()" style="background: #27ae60;">💾 Save Settings</button>
        <button onclick="startRun()" style="background: #27ae60;">🚀 Start Search</button>
        <button onclick="clearDatabase()" style="background: #e74c3c;">🗑️ Clear Old Jobs</button>
        <div id="run-status"></div>
    </section>

    <script>
        const STORAGE_KEY = 'jobAgentConfig';

        function loadSettings() {
            const config = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            document.getElementById('roles').value = (config.roles || []).join('\n');
            document.getElementById('locations').value = (config.locations || []).join('\n');
            document.getElementById('cv_text').value = config.cv_text || '';
            document.getElementById('match_threshold').value = config.match_threshold || 0.75;
            ['linkedin', 'stepstone', 'xing'].forEach(s => {
                const checked = !config.enabled_scrapers || config.enabled_scrapers.includes(s);
                document.getElementById('scraper_' + s).checked = checked;
            });
        }

        function saveSettings() {
            const enabledScrapers = ['linkedin', 'stepstone', 'xing']
                .filter(s => document.getElementById('scraper_' + s).checked);
            const config = {
                roles: document.getElementById('roles').value.split('\n').filter(r => r.trim()),
                locations: document.getElementById('locations').value.split('\n').filter(l => l.trim()),
                cv_text: document.getElementById('cv_text').value,
                match_threshold: parseFloat(document.getElementById('match_threshold').value) || 0.75,
                enabled_scrapers: enabledScrapers,
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
            showStatus('✅ Settings saved to browser cache', 'success');
        }

        function showStatus(msg, cls) {
            const status = document.getElementById('status');
            status.textContent = msg;
            status.className = cls;
        }

        async function uploadCV(mode) {
            const formData = new FormData();
            let cvText = null;

            if (mode === 'file') {
                const file = document.getElementById('cv_file').files[0];
                if (!file) {
                    alert('Please select a PDF file');
                    return;
                }
                formData.append('cv_file', file);
            } else {
                cvText = document.getElementById('cv_text').value;
                if (!cvText.trim()) {
                    alert('Please paste some CV text');
                    return;
                }
                formData.append('cv_text', cvText);
            }

            try {
                const r = await fetch('/upload-cv', { method: 'POST', body: formData });
                const data = await r.json();
                if (data.ok) {
                    const config = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
                    config.cv_text = data.cv_text;
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
                    document.getElementById('cv_text').value = data.cv_text;
                    showStatus('✅ CV saved (' + data.cv_text.length + ' characters)', 'success');
                } else {
                    showStatus('❌ Error: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (e) {
                showStatus('❌ Error: ' + e.message, 'error');
            }
        }

        async function startRun() {
            const config = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            if (!config.roles || config.roles.length === 0) {
                alert('Please add at least one role keyword before starting search');
                return;
            }
            if (!config.locations || config.locations.length === 0) {
                alert('Please add at least one location before starting search');
                return;
            }
            try {
                const r = await fetch('/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(config),
                });
                const data = await r.json();
                const status = document.getElementById('run-status');
                if (data.ok) {
                    status.innerHTML = '✅ Search started! Check the <a href="/">Job Digest</a> to see results.';
                } else {
                    status.textContent = '⚠️ ' + (data.error || 'Could not start search');
                }
            } catch (e) {
                document.getElementById('run-status').textContent = '❌ Error: ' + e.message;
            }
        }

        async function clearDatabase() {
            if (!confirm('Clear all old jobs from the database? You will only see new jobs from your next search.')) {
                return;
            }
            try {
                const r = await fetch('/clear-db', { method: 'POST' });
                const data = await r.json();
                const status = document.getElementById('run-status');
                if (data.ok) {
                    status.textContent = '✅ Old jobs cleared! Next search will start fresh.';
                } else {
                    status.textContent = '❌ Error: ' + (data.error || 'Could not clear database');
                }
            } catch (e) {
                document.getElementById('run-status').textContent = '❌ Error: ' + e.message;
            }
        }

        async function showCurrentCV() {
            const config = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            const preview = document.getElementById('cv-preview');
            const cvText = config.cv_text || '';
            if (cvText) {
                preview.textContent = cvText.substring(0, 1000);
                if (cvText.length > 1000) {
                    preview.textContent += '\n\n... (' + (cvText.length - 1000) + ' more characters)';
                }
                preview.style.display = 'block';
            } else {
                preview.textContent = 'No CV loaded';
                preview.style.display = 'block';
            }
        }

        async function clearCV() {
            if (!confirm('Clear the uploaded CV? You will need to upload a new one.')) {
                return;
            }
            try {
                const config = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
                config.cv_text = '';
                localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
                document.getElementById('cv_text').value = '';
                showStatus('✅ CV cleared. Upload a new one.', 'success');
                document.getElementById('cv-preview').style.display = 'none';
            } catch (e) {
                showStatus('❌ Error: ' + e.message, 'error');
            }
        }

        window.addEventListener('load', loadSettings);
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
        elif self.path == "/upload-cv":
            content_type = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            try:
                if "multipart/form-data" in content_type:
                    boundary = content_type.split("boundary=")[1].split(";")[0].encode()
                    parts = body.split(b"--" + boundary)

                    cv_text = ""
                    for part in parts:
                        if b"filename=" in part:
                            if b".pdf" in part.lower():
                                start = part.find(b"\r\n\r\n") + 4
                                end = part.rfind(b"\r\n")
                                pdf_bytes = part[start:end]
                                try:
                                    cv_text = extract_pdf_text(pdf_bytes)
                                except Exception as e:
                                    raise ValueError(f"PDF parse error: {e}")
                        elif b'name="cv_text"' in part:
                            start = part.find(b"\r\n\r\n") + 4
                            end = part.rfind(b"\r\n")
                            cv_text = part[start:end].decode("utf-8")

                    if cv_text:
                        response = json.dumps({"ok": True, "cv_text": cv_text}).encode()
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
                length = int(self.headers.get("Content-Length", 0))
                config = json.loads(self.rfile.read(length)) if length else {}
                print(f"[Server /run] Received config: roles={config.get('roles', [])}, cv_text_len={len(config.get('cv_text', ''))}, scrapers={config.get('enabled_scrapers', [])}")

                def run_pipeline_bg():
                    from main import run_pipeline
                    _state["processing"] = True
                    try:
                        asyncio.run(run_pipeline(config, test_mode=False, start_server=False))
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
        pass


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
