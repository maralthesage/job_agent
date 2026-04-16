#!/usr/bin/env python3
"""
main.py — Job Agent entry point
Orchestrates: scrape → deduplicate → score → html digest

Usage:
  python main.py              # full run
  python main.py --test       # run with mock data (no real scraping)
  python main.py --from-db    # view saved jobs without re-scraping
"""
import asyncio
import argparse
import time
from datetime import datetime

from core.db import init_db, is_seen, mark_seen, update_job_score, log_digest
from core.agent import score_job
from core.server import serve_digest, start_server_thread, set_done
from core.filters import title_matches, MATCH_THRESHOLD
from core.user_config import load_config


# ── Config ──────────────────────────────────────────────────────────────────
MAX_JOBS_PER_SOURCE = 20


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ── Scrapers ─────────────────────────────────────────────────────────────────
async def run_scrapers(on_job=None, roles=None, locations=None) -> list:
    from scrapers.linkedin import scrape_linkedin
    from scrapers.stepstone import scrape_stepstone
    from scrapers.xing import scrape_xing

    log("Starting scrapers...")
    results = await asyncio.gather(
        scrape_linkedin(MAX_JOBS_PER_SOURCE, on_job=on_job, roles=roles, locations=locations),
        scrape_stepstone(MAX_JOBS_PER_SOURCE, on_job=on_job, roles=roles, locations=locations),
        scrape_xing(MAX_JOBS_PER_SOURCE, on_job=on_job, roles=roles, locations=locations),
        return_exceptions=True
    )

    all_jobs = []
    sources = ["LinkedIn", "Stepstone", "Xing"]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log(f"[{sources[i]}] scraper failed: {result}")
        else:
            log(f"[{sources[i]}] found {len(result)} listings")
            all_jobs.extend(result)

    return all_jobs


def mock_jobs() -> list:
    """Returns fake jobs for --test mode."""
    return [
        {
            "id": "test_001",
            "source": "linkedin",
            "title": "Data Scientist",
            "company": "Test GmbH",
            "location": "Düsseldorf, Germany",
            "url": "https://linkedin.com/jobs/test",
            "description": (
                "We are looking for a Data Scientist with experience in Python, "
                "XGBoost, LightGBM, and data pipelines. Experience with PySpark, "
                "ETL, and Streamlit dashboards is a plus. You will develop ML models "
                "for demand forecasting and build scalable data solutions. "
                "German B2 level preferred."
            ),
        },
        {
            "id": "test_002",
            "source": "indeed",
            "title": "Senior Data Analyst",
            "company": "Analytics Corp",
            "location": "Remote (Germany)",
            "url": "https://indeed.de/jobs/test2",
            "description": (
                "Senior Data Analyst role. Requirements: SQL, Python, Tableau or "
                "Power BI, statistical analysis. Nice to have: machine learning "
                "experience, LangChain, RAG systems, stakeholder management. "
                "English C1 required."
            ),
        },
    ]


# ── Main pipeline ─────────────────────────────────────────────────────────────
async def run_pipeline(config: dict, test_mode: bool = False, start_server: bool = True):
    """
    Core job agent pipeline.

    Args:
        config: user config dict with roles, locations, cv_text, match_threshold
        test_mode: if True, use mock jobs instead of scraping
        start_server: if True, start the HTTP server (set False when called from dashboard)
    """
    log("=" * 55)
    log("Job Agent starting")
    log("=" * 55)

    init_db()

    # Extract config values
    roles = config.get("roles", [])
    locations = config.get("locations", [])
    cv_text = config.get("cv_text", "")
    match_threshold = config.get("match_threshold", MATCH_THRESHOLD)
    title_keywords = [kw.lower() for kw in roles]  # Use roles as title keywords

    # DEBUG: Log what we loaded
    log(f"Loaded config: roles={roles}, cv_text_len={len(cv_text) if cv_text else 0}, threshold={match_threshold}")

    # Step 1: Start live digest server (unless already running from dashboard)
    httpd = None
    if start_server:
        httpd = start_server_thread()
        log("Started HTTP server for digest")

    # Step 2: Scrape — save each new job to DB as soon as it's found
    newly_scraped = []

    def save_if_new(job):
        if not is_seen(job["id"]):
            mark_seen(job)          # saved with score=0, visible in digest right away
            newly_scraped.append(job)

    if test_mode:
        log("TEST MODE – using mock jobs")
        for job in mock_jobs():
            save_if_new(job)
    else:
        await run_scrapers(on_job=save_if_new, roles=roles, locations=locations)

    log(f"Scraped {len(newly_scraped)} new jobs")

    if not newly_scraped:
        log("No new jobs to score.")
        log_digest(0, "no_new_jobs")
        set_done()
    else:
        # Step 3: Score only jobs with relevant titles (skip LLM call for irrelevant ones)
        to_score = [j for j in newly_scraped if title_matches(j.get("title", ""), keywords=title_keywords if title_keywords else None)]
        skipped = len(newly_scraped) - len(to_score)
        if skipped:
            log(f"Skipping {skipped} jobs with non-matching titles")

        for i, job in enumerate(to_score):
            log(f"Scoring [{i+1}/{len(to_score)}]: {job['title']} @ {job['company']}")
            score, details = score_job(job, threshold=match_threshold, cv_text=cv_text if cv_text else None, target_roles=roles)
            job["match_score"] = score
            update_job_score(job["id"], score)  # page auto-refreshes with new score
            log(f"  → {int(score*100)}% — {details.get('reason', '')}")

        matched_count = sum(1 for j in to_score if j.get("match_score", 0) >= match_threshold)
        log(f"\nScored {len(to_score)} relevant jobs, {matched_count} above {int(match_threshold*100)}%")
        log_digest(len(to_score), "sent")
        set_done()

    log("=" * 55)
    if start_server:
        log("Done. Digest server running — press Ctrl+C to stop.")
        log("=" * 55)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.server_close()
    else:
        log("Done. Digest will refresh automatically.")
        log("=" * 55)


async def run(test_mode: bool = False):
    """Load config and run the pipeline."""
    config = load_config()
    await run_pipeline(config, test_mode=test_mode)


def run_from_db(days: int = 30):
    """Serve saved jobs from DB as interactive HTML digest."""
    init_db()
    log(f"Starting digest server for last {days} days (Ctrl+C to stop)...")
    serve_digest(days=days)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Job Agent")
    parser.add_argument("--test", action="store_true", help="Use mock jobs (no real scraping)")
    parser.add_argument("--from-db", action="store_true", help="Show saved jobs from DB as HTML digest")
    parser.add_argument("--days", type=int, default=30, help="How many days back to show (with --from-db)")
    args = parser.parse_args()

    if args.from_db:
        run_from_db(days=args.days)
    else:
        asyncio.run(run(test_mode=args.test))
