"""
emailer.py — Builds the job digest and opens it as an HTML file in the browser
"""
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import List, Dict


OUTPUT_DIR = Path(__file__).parent.parent / "output" / "digests"


def score_bar(score: float) -> str:
    filled = round(score * 10)
    return "█" * filled + "░" * (10 - filled)


def score_color(score: float) -> str:
    if score >= 0.80:
        return "#16a34a"  # green
    elif score >= 0.65:
        return "#d97706"  # amber
    else:
        return "#6b7280"  # gray


from core.filters import MATCH_THRESHOLD


def build_html(jobs: List[Dict]) -> str:
    import json as _json
    now = datetime.now().strftime("%A, %d %B %Y – %H:%M")
    count = len(jobs)
    matched_count = sum(1 for j in jobs if j.get("match_score", 0) >= MATCH_THRESHOLD)

    job_cards = ""
    for job in jobs:
        score = job.get("match_score", 0.0)
        pct = int(score * 100)
        color = score_color(score)
        bar = score_bar(score)
        applied = bool(job.get("applied", 0))
        job_id_js = _json.dumps(job.get("id", ""))

        card_opacity = "0.5" if applied else "1"
        applied_badge = (
            '<span class="applied-badge" style="background:#dcfce7;color:#166534;font-size:11px;'
            'padding:2px 8px;border-radius:10px;">✓ Applied</span>'
        )
        if not applied:
            applied_badge = (
                '<span class="applied-badge" style="display:none;background:#dcfce7;color:#166534;'
                'font-size:11px;padding:2px 8px;border-radius:10px;">✓ Applied</span>'
            )

        # Description snippet
        desc = job.get("description", "")
        snippet = (desc[:220] + "…") if len(desc) > 220 else desc
        snippet_html = (
            f'<p style="margin:8px 0 4px;font-size:13px;color:#374151;'
            f'line-height:1.5;background:#f9fafb;padding:8px 10px;border-radius:6px;">'
            f'{snippet}</p>'
        ) if snippet else ""

        missing = job.get("missing_skills", [])
        missing_html = ""
        if missing:
            tags = "".join(
                f'<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                f'font-size:11px;padding:2px 8px;border-radius:10px;margin:2px;">{s}</span>'
                for s in missing[:5]
            )
            missing_html = f'<p style="margin:6px 0 0;font-size:12px;color:#6b7280;">Gaps: {tags}</p>'

        matching = job.get("matching_skills", [])
        matching_html = ""
        if matching:
            tags = "".join(
                f'<span style="display:inline-block;background:#d1fae5;color:#065f46;'
                f'font-size:11px;padding:2px 8px;border-radius:10px;margin:2px;">{s}</span>'
                for s in matching[:6]
            )
            matching_html = f'<p style="margin:6px 0 0;font-size:12px;color:#6b7280;">Matches: {tags}</p>'

        reason = job.get("reason", "")
        source_badge = (
            f'<span style="background:#e0e7ff;color:#3730a3;font-size:11px;'
            f'padding:2px 8px;border-radius:10px;">{job.get("source","").upper()}</span>'
        )
        threshold_badge = (
            f'<span style="background:#dcfce7;color:#166534;font-size:11px;'
            f'padding:2px 8px;border-radius:10px;">Good match</span>'
            if score >= MATCH_THRESHOLD else
            f'<span style="background:#f3f4f6;color:#6b7280;font-size:11px;'
            f'padding:2px 8px;border-radius:10px;">Below threshold</span>'
        )
        checked_attr = "checked" if applied else ""

        job_cards += f"""
        <div class="job-card" style="border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:16px 0;
                    background:#ffffff;border-left:4px solid {color};opacity:{card_opacity};
                    transition:opacity 0.2s;">
          <div style="display:flex;align-items:flex-start;gap:12px;">
            <label style="display:flex;align-items:center;margin-top:3px;cursor:pointer;flex-shrink:0;"
                   title="Mark as applied">
              <input type="checkbox" {checked_attr}
                     data-job-id={job_id_js}
                     onchange="toggleApplied(this)"
                     style="width:18px;height:18px;cursor:pointer;accent-color:#16a34a;">
            </label>
            <div style="flex:1;min-width:0;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div>
                  <h3 style="margin:0 0 4px;font-size:17px;color:#111827;">{job.get('title','')}</h3>
                  <p style="margin:0;color:#4b5563;font-size:14px;">
                    {job.get('company','')} &nbsp;·&nbsp; {job.get('location','')}
                  </p>
                </div>
                <div style="text-align:right;flex-shrink:0;margin-left:16px;">
                  <span style="font-size:24px;font-weight:700;color:{color};">{pct}%</span>
                  <p style="margin:2px 0 0;font-family:monospace;font-size:11px;color:{color};">{bar}</p>
                </div>
              </div>
              <p style="margin:10px 0 4px;font-size:13px;color:#6b7280;font-style:italic;">{reason}</p>
              {snippet_html}
              {matching_html}
              {missing_html}
              <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                {source_badge}
                {threshold_badge}
                {applied_badge}
                <a href="{job.get('url','#')}" target="_blank" rel="noopener noreferrer"
                   style="background:#2563eb;color:#fff;padding:6px 16px;border-radius:8px;
                          text-decoration:none;font-size:13px;font-weight:500;">
                  View Job →
                </a>
              </div>
            </div>
          </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <script>
        // Live update: poll /status and reload when new jobs arrive
        let _knownCount = null;
        async function _poll() {{
          try {{
            const r = await fetch('/status');
            const s = await r.json();
            if (_knownCount === null) _knownCount = s.count;
            if (s.count !== _knownCount) {{ location.reload(); return; }}
            const bar = document.getElementById('live-bar');
            if (s.processing) {{
              bar.style.display = 'block';
              bar.textContent = 'Scraping in progress\u2026 ' + s.count + ' jobs found so far';
              setTimeout(_poll, 3000);
            }} else {{
              bar.style.display = 'none';
            }}
          }} catch(e) {{ /* server not reachable, stop polling */ }}
        }}
        _poll();

        async function toggleApplied(checkbox) {{
          const jobId = checkbox.dataset.jobId;
          const applied = checkbox.checked;
          const card = checkbox.closest('.job-card');
          const badge = card.querySelector('.applied-badge');
          try {{
            const resp = await fetch('/apply', {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify({{id: jobId, applied: applied}})
            }});
            if (!resp.ok) throw new Error('Server error');
            card.style.opacity = applied ? '0.5' : '1';
            badge.style.display = applied ? 'inline-block' : 'none';
          }} catch(e) {{
            checkbox.checked = !applied;
            alert('Could not save. Is the job agent server running?');
          }}
        }}

        function clearCache() {{
          if (confirm('Clear all saved preferences and browser cache?')) {{
            localStorage.removeItem('jobAgentConfig');
            alert('Cache cleared. Your preferences have been reset.');
          }}
        }}
      </script>
    </head>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                 background:#f9fafb;margin:0;padding:20px;">
      <div style="max-width:720px;margin:0 auto;">

        <!-- Live scraping banner -->
        <div id="live-bar" style="display:none;background:#fef9c3;color:#854d0e;
             border-radius:10px;padding:10px 16px;margin-bottom:12px;
             font-size:13px;font-weight:500;text-align:center;"></div>

        <!-- Navigation -->
        <div style="margin-bottom:20px;display:flex;gap:16px;justify-content:space-between;">
          <div style="display:flex;gap:16px;">
            <a href="/" style="color:#2563eb;text-decoration:none;font-weight:500;">📊 Job Digest</a>
            <a href="/settings" style="color:#2563eb;text-decoration:none;font-weight:500;">⚙ Settings</a>
          </div>
          <button onclick="clearCache()" style="background:#e74c3c;color:white;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-weight:500;font-size:13px;">🗑️ Clear Cache</button>
        </div>

        <!-- Header -->
        <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);
                    border-radius:16px;padding:28px;margin-bottom:24px;color:#fff;">
          <h1 style="margin:0 0 6px;font-size:22px;">Job Digest</h1>
          <p style="margin:0;opacity:0.85;font-size:14px;">{now}</p>
          <p style="margin:8px 0 0;font-size:28px;font-weight:700;">{count} job{"s" if count != 1 else ""}</p>
          <p style="margin:4px 0 0;opacity:0.75;font-size:13px;">
            {matched_count} above {int(MATCH_THRESHOLD*100)}% match
          </p>
        </div>

        <!-- Jobs -->
        {job_cards if job_cards else
         '<p style="text-align:center;color:#6b7280;padding:40px;">No jobs found.</p>'}

        <!-- Footer -->
        <div style="text-align:center;padding:24px;color:#9ca3af;font-size:12px;">
          <p>Job Agent · sorted by match score · check a job to mark as applied</p>
        </div>
      </div>
    </body>
    </html>
    """
    return html


def send_digest(jobs: List[Dict]) -> bool:
    """Save job digest as HTML and open it in the browser. Returns True on success."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = OUTPUT_DIR / f"digest_{timestamp}.html"
        out_path.write_text(build_html(jobs), encoding="utf-8")
        webbrowser.open(out_path.as_uri())
        print(f"[Digest] Opened in browser: {out_path}")
        return True
    except Exception as e:
        print(f"[Digest] Failed to open HTML: {e}")
        return False
