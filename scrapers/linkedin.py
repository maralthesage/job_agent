"""
linkedin.py — LinkedIn job scraper via Playwright (headless browser)
Scrapes job listings for Data Scientist / Data Analyst roles in NRW + remote.
"""
import asyncio
import hashlib
import re
from typing import List, Dict


BASE_URL = "https://www.linkedin.com/jobs/search"


def make_job_id(url: str) -> str:
    return "linkedin_" + hashlib.md5(url.encode()).hexdigest()[:12]


async def scrape_linkedin(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrapes LinkedIn job listings using Playwright.
    Returns list of job dicts with title, company, location, url, description.

    Args:
        max_jobs: maximum jobs to return
        on_job: callback function called when a job is found
        roles: list of role keywords (required)
        locations: list of locations (required)
    """
    if not roles or not locations:
        print("[LinkedIn] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[LinkedIn] playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    # Build queries from user-provided roles and locations
    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="keywords", key_loc="location")

    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )

        for query in queries:
            if len(jobs) >= max_jobs:
                break
            try:
                page = await context.new_page()
                params = (
                    f"?keywords={query['keywords'].replace(' ', '%20')}"
                    f"&location={query['location'].replace(' ', '%20')}"
                    f"&f_WT=2"          # remote filter
                    f"&sortBy=DD"       # most recent first
                    f"&f_TPR=r1209600"  # posted in last 2 weeks (14 days * 86400s)
                )
                await page.goto(BASE_URL + params, timeout=30000)
                await page.wait_for_timeout(3000)

                # Scroll to load more listings
                for _ in range(3):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1500)

                cards = await page.query_selector_all(".job-search-card")

                for card in cards[:10]:
                    try:
                        title_el = await card.query_selector(".base-search-card__title")
                        company_el = await card.query_selector(".base-search-card__subtitle")
                        location_el = await card.query_selector(".job-search-card__location")
                        link_el = await card.query_selector("a.base-card__full-link")

                        title = (await title_el.inner_text()).strip() if title_el else ""
                        company = (await company_el.inner_text()).strip() if company_el else ""
                        location = (await location_el.inner_text()).strip() if location_el else ""
                        url = await link_el.get_attribute("href") if link_el else ""

                        if not title or not url:
                            continue

                        # Fetch job description
                        description = ""
                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(url, timeout=20000)
                            await detail_page.wait_for_timeout(2000)
                            desc_el = await detail_page.query_selector(".show-more-less-html__markup")
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id(url),
                            "source": "linkedin",
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
                        print(f"[LinkedIn] card parse error: {e}")
                        continue

                await page.close()
                await asyncio.sleep(2)  # polite delay

            except Exception as e:
                print(f"[LinkedIn] query error for '{query}': {e}")
                continue

        await browser.close()

    return jobs
