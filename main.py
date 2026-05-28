#!/usr/bin/env python3
"""
main.py — Job Agent entry point
Orchestrates: scrape → deduplicate → score → html digest

Usage:
  python main.py              # start the local browser UI
  python main.py --run --test # run mock jobs through the scoring pipeline
  python main.py --run        # run a search from data/user_config.json
"""
import asyncio
import argparse
import time
from datetime import datetime

from core.db import init_db, is_seen, mark_seen, update_job_score, log_digest
from core.server import serve_digest, start_server_thread, set_done
from core.filters import description_matches, title_matches, MATCH_THRESHOLD
from core.user_config import load_config


# ── Config ──────────────────────────────────────────────────────────────────
MAX_JOBS_PER_SOURCE = 20


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ── Scrapers ─────────────────────────────────────────────────────────────────
async def run_scrapers(on_job=None, roles=None, locations=None, enabled_scrapers=None) -> list:
    from scrapers.linkedin import scrape_linkedin
    from scrapers.stepstone import scrape_stepstone
    from scrapers.xing import scrape_xing

    log("Starting scrapers...")
    scrapers_map = {
        "linkedin": (scrape_linkedin, "LinkedIn"),
        "stepstone": (scrape_stepstone, "Stepstone"),
        "xing": (scrape_xing, "Xing"),
    }

    active = enabled_scrapers if enabled_scrapers else ["linkedin", "stepstone", "xing"]
    tasks = {}
    for scraper_name in active:
        if scraper_name in scrapers_map:
            scraper_fn, label = scrapers_map[scraper_name]
            tasks[scraper_name] = (scraper_fn, label)

    if not tasks:
        log("No active scrapers available")
        return []

    semaphore = asyncio.Semaphore(3)

    async def run_one(scraper_fn):
        async with semaphore:
            return await scraper_fn(
                MAX_JOBS_PER_SOURCE,
                on_job=on_job,
                roles=roles,
                locations=locations,
            )

    results = await asyncio.gather(
        *[run_one(task[0]) for task in tasks.values()],
        return_exceptions=True
    )

    all_jobs = []
    for i, (scraper_name, (_, label)) in enumerate(tasks.items()):
        result = results[i]
        if isinstance(result, Exception):
            log(f"[{label}] scraper failed: {result}")
        else:
            log(f"[{label}] found {len(result)} listings")
            all_jobs.extend(result)

    return all_jobs


def mock_jobs() -> list:
    """Returns fake jobs for --test mode."""
    return [
        {
            "id": "test_001",
            "source": "test_source",
            "title": "Test Role 1",
            "company": "Test Company 1",
            "location": "Test Location",
            "url": "https://example.com/test1",
            "description": "This is a test job description for testing purposes.",
        },
        {
            "id": "test_002",
            "source": "test_source",
            "title": "Test Role 2",
            "company": "Test Company 2",
            "location": "Test Location 2",
            "url": "https://example.com/test2",
            "description": "Another test job description for testing the pipeline.",
        },
    ]


# ── Main pipeline ─────────────────────────────────────────────────────────────
async def run_pipeline(config: dict, test_mode: bool = False, start_server: bool = True):
    """
    Core job agent pipeline.

    Args:
        config: user config dict with roles, description_keywords, locations, cv_text, match_threshold
        test_mode: if True, use mock jobs instead of scraping
        start_server: if True, start the HTTP server (set False when called from dashboard)
    """
    log("=" * 55)
    log("Job Agent starting")
    log("=" * 55)

    init_db()

    roles = [str(role).strip() for role in config.get("roles", []) if str(role).strip()]
    description_keywords = [
        str(keyword).strip()
        for keyword in config.get("description_keywords", [])
        if str(keyword).strip()
    ]
    locations = [str(location).strip() for location in config.get("locations", []) if str(location).strip()]
    cv_text = config.get("cv_text", "")
    match_threshold = config.get("match_threshold", MATCH_THRESHOLD)
    enabled_scrapers = config.get("enabled_scrapers", ["linkedin", "stepstone", "xing"])
    title_keywords = [kw.lower() for kw in roles]

    # DEBUG: Log what we loaded
    log(
        f"Loaded config: roles={roles}, description_keywords={description_keywords}, "
        f"cv_text_len={len(cv_text) if cv_text else 0}, threshold={match_threshold}"
    )

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
        await run_scrapers(on_job=save_if_new, roles=roles, locations=locations, enabled_scrapers=enabled_scrapers)

    log(f"Scraped {len(newly_scraped)} new jobs")

    if not newly_scraped:
        log("No new jobs to score.")
        log_digest(0, "no_new_jobs")
        set_done()
    else:
        # Step 3: Score only jobs with relevant titles and description keywords
        title_matched = [
            j for j in newly_scraped
            if title_matches(j.get("title", ""), keywords=title_keywords if title_keywords else None)
        ]
        skipped_titles = len(newly_scraped) - len(title_matched)
        if skipped_titles:
            log(f"Skipping {skipped_titles} jobs with non-matching titles")

        to_score = [
            j for j in title_matched
            if description_matches(j.get("description", ""), keywords=description_keywords)
        ]
        skipped_descriptions = len(title_matched) - len(to_score)
        if skipped_descriptions:
            log(f"Skipping {skipped_descriptions} jobs without required description keywords")

        from core.agent import score_job

        for i, job in enumerate(to_score):
            log(f"Scoring [{i+1}/{len(to_score)}]: {job['title']} @ {job['company']}")
            score, details = score_job(
                job,
                threshold=match_threshold,
                cv_text=cv_text if cv_text else None,
                target_roles=roles,
                target_description_keywords=description_keywords,
            )
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
    parser.add_argument("--test", action="store_true", help="Use mock jobs with --run")
    parser.add_argument("--run", action="store_true", help="Run the pipeline from data/user_config.json")
    parser.add_argument("--days", type=int, default=30, help="How many days back to show")
    args = parser.parse_args()

    if args.run:
        asyncio.run(run(test_mode=args.test))
    else:
        # Default: start in settings/digest mode, scraping only happens when user clicks "Start Search"
        run_from_db(days=args.days)
