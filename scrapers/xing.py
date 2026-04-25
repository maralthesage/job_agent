"""
xing.py — Xing job scraper via Playwright
Xing is popular for German-speaking markets; good for NRW roles.
"""
import asyncio
import hashlib
import re
from typing import List, Dict


def _is_within_14_days(time_text: str) -> bool:
    """Parse Xing's German time-ago strings and return True if posted within 14 days."""
    if not time_text:
        return True  # unknown, include it
    t = time_text.lower()
    if any(w in t for w in ("stunde", "minute", "sekunde", "heute", "gestern")):
        return True
    if "tag" in t:
        m = re.search(r"(\d+)", t)
        return int(m.group(1)) <= 14 if m else True
    if "woche" in t:
        m = re.search(r"(\d+)", t)
        return int(m.group(1)) <= 2 if m else False  # >2 weeks = too old
    if "monat" in t or "jahr" in t:
        return False
    return True


BASE_URL = "https://www.xing.com/jobs/search"


def make_job_id(url: str) -> str:
    return "xing_" + hashlib.md5(url.encode()).hexdigest()[:12]


async def scrape_xing(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrapes Xing job listings.
    Returns list of job dicts.

    Args:
        max_jobs: maximum jobs to return
        on_job: callback function called when a job is found
        roles: list of role keywords (required)
        locations: list of locations (required)
    """
    if not roles or not locations:
        print("[Xing] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Xing] playwright not installed.")
        return []

    # Build queries from user-provided roles and locations
    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="q", key_loc="location")

    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            locale="de-DE"
        )

        for query in queries:
            if len(jobs) >= max_jobs:
                break
            try:
                page = await context.new_page()
                params = (
                    f"?keywords={query['q'].replace(' ', '%20')}"
                    f"&location={query['location'].replace(' ', '%20')}"
                    f"&sort=date"
                )
                await page.goto(BASE_URL + params, timeout=30000)
                await page.wait_for_timeout(4000)

                # Handle cookie consent
                try:
                    consent = await page.query_selector(
                        "button[data-testid='consent-accept-btn'], "
                        "button[class*='consent'], button[id*='accept']"
                    )
                    if consent:
                        await consent.click()
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass

                # Scroll to load listings
                for _ in range(2):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1500)

                cards = await page.query_selector_all(
                    "[data-testid='job-posting-preview'], "
                    ".jobs-job-teaser, article[class*='job']"
                )

                for card in cards[:8]:
                    try:
                        title_el = await card.query_selector(
                            "h2, h3, [data-testid='job-title'], a[class*='title']"
                        )
                        company_el = await card.query_selector(
                            "[data-testid='company-name'], [class*='company'], a[class*='company']"
                        )
                        location_el = await card.query_selector(
                            "[data-testid='location'], [class*='location']"
                        )
                        time_el = await card.query_selector(
                            "time, [data-testid='published-at'], [class*='date'], [class*='time']"
                        )

                        title = (await title_el.inner_text()).strip() if title_el else ""
                        company = (await company_el.inner_text()).strip() if company_el else ""
                        location = (await location_el.inner_text()).strip() if location_el else ""
                        time_text = (await time_el.inner_text()).strip() if time_el else ""

                        # Skip jobs older than 14 days
                        if not _is_within_14_days(time_text):
                            continue

                        # Get job URL: prefer link wrapping the title, then any jobs/ link
                        link_el = await card.query_selector(
                            "h2 a[href], h3 a[href], "
                            "a[data-testid='job-title-link'], "
                            "a[href*='/jobs/'][href*='-']"
                        )
                        href = await link_el.get_attribute("href") if link_el else ""
                        url = (
                            f"https://www.xing.com{href}"
                            if href and href.startswith("/")
                            else href
                        )

                        if not title or not url:
                            continue

                        # Fetch job description
                        description = ""
                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(url, timeout=20000)
                            await detail_page.wait_for_timeout(2000)
                            desc_el = await detail_page.query_selector(
                                "[data-testid='job-description'], "
                                "[class*='description'], main article"
                            )
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id(url),
                            "source": "xing",
                            "title": title,
                            "company": company,
                            "location": location,
                            "url": url,
                            "description": description,
                        }
                        jobs.append(job)
                        if on_job:
                            on_job(job)

                    except Exception as e:
                        print(f"[Xing] card parse error: {e}")
                        continue

                await page.close()
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[Xing] query error: {e}")
                continue

        await browser.close()

    return jobs
