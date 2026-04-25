"""
stepstone.py — Stepstone.de job scraper via Playwright
"""
import asyncio
import hashlib
from typing import List, Dict


BASE_URL = "https://www.stepstone.de/jobs/"


def make_job_id(url: str) -> str:
    return "stepstone_" + hashlib.md5(url.encode()).hexdigest()[:12]


async def scrape_stepstone(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrapes Stepstone.de for jobs.
    Returns list of job dicts.

    Args:
        max_jobs: maximum jobs to return
        on_job: callback function called when a job is found
        roles: list of role keywords (required)
        locations: list of locations (required)
    """
    if not roles or not locations:
        print("[Stepstone] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Stepstone] playwright not installed.")
        return []

    # Build queries from user-provided roles and locations
    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="q", key_loc="where")

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
                keyword = query["q"].replace(" ", "+")
                location = query["where"].replace(" ", "+")
                # sort=2 = most recent; dateRange=14 = last 14 days
                url = f"{BASE_URL}?q={keyword}&where={location}&sort=2&dateRange=14"
                await page.goto(url, timeout=30000)
                await page.wait_for_timeout(3000)

                # Handle cookie consent
                try:
                    consent = await page.query_selector(
                        "button[data-at='cookie-consent-accept-all-button'], "
                        "button[data-genesis-element='BASE_BUTTON'][class*='accept'], "
                        "button[id*='accept-all']"
                    )
                    if consent:
                        await consent.click()
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass

                # Scroll to load more listings
                for _ in range(2):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1500)

                cards = await page.query_selector_all(
                    "article[data-at='job-item'], "
                    "article[data-testid='job-item'], "
                    "article[class*='ResultsList']"
                )

                for card in cards[:8]:
                    try:
                        # Title + link: title link is the canonical job URL
                        link_el = await card.query_selector(
                            "h2 a[href*='/stellenangebote/'], "
                            "a[data-at='job-item-title'][href], "
                            "h2 a[href], h3 a[href]"
                        )
                        company_el = await card.query_selector(
                            "[data-at='job-item-company-name'], "
                            "a[data-at*='company'], "
                            "span[data-genesis-element='SUBTITLE'] a, "
                            "span[class*='company']"
                        )
                        location_el = await card.query_selector(
                            "[data-at='job-item-location'], "
                            "li[data-genesis-element='LOCATION'], "
                            "span[data-genesis-element='LOCATION'], "
                            "li[class*='location']"
                        )

                        if not link_el:
                            continue

                        title = (await link_el.inner_text()).strip()
                        company = (await company_el.inner_text()).strip() if company_el else ""
                        location_text = (await location_el.inner_text()).strip() if location_el else ""
                        href = await link_el.get_attribute("href")
                        job_url = (
                            f"https://www.stepstone.de{href}"
                            if href and href.startswith("/")
                            else href or ""
                        )

                        if not title or not job_url:
                            continue

                        # Fetch job description from detail page
                        description = ""
                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(job_url, timeout=20000)
                            await detail_page.wait_for_timeout(2000)
                            desc_el = await detail_page.query_selector(
                                "[data-at='jobad-description'], "
                                "[class*='jobad-body--description'], "
                                "div[class*='at-section-text'], "
                                "main section"
                            )
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id(job_url),
                            "source": "stepstone",
                            "title": title,
                            "company": company,
                            "location": location_text,
                            "url": job_url,
                            "description": description,
                        }
                        jobs.append(job)
                        if on_job:
                            on_job(job)

                    except Exception as e:
                        print(f"[Stepstone] card parse error: {e}")
                        continue

                await page.close()
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[Stepstone] query error: {e}")
                continue

        await browser.close()

    return jobs
