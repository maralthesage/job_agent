"""
indeed.py — Indeed job scraper via Playwright.
"""
import asyncio
from typing import Dict, List

from scrapers.common import (
    DEFAULT_USER_AGENT,
    absolute_url,
    accept_common_cookie_banners,
    clean_text,
    make_job_id,
    quote_query,
)


BASE_URL = "https://www.indeed.com/jobs"


async def scrape_indeed(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrape Indeed search results.

    Args:
        max_jobs: maximum jobs to return
        on_job: callback function called when a job is found
        roles: list of role keywords (required)
        locations: list of locations (required)
    """
    if not roles or not locations:
        print("[Indeed] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Indeed] playwright not installed.")
        return []

    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="q", key_loc="l")

    jobs = []
    seen_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="en-US")

        for query in queries:
            if len(jobs) >= max_jobs:
                break
            page = await context.new_page()
            try:
                url = (
                    f"{BASE_URL}?q={quote_query(query['q'])}"
                    f"&l={quote_query(query['l'])}"
                    "&fromage=14&sort=date"
                )
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                await accept_common_cookie_banners(page)
                body_text = ""
                try:
                    body_text = await page.locator("body").inner_text(timeout=3000)
                except Exception:
                    pass
                if "Additional Verification Required" in body_text or "Just a moment" in await page.title():
                    print("[Indeed] blocked by verification page; skipping query")
                    continue

                for _ in range(2):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1200)

                cards = await page.query_selector_all(
                    "div.job_seen_beacon, "
                    "td.resultContent, "
                    "div[data-jk], "
                    "li:has(a[href*='/rc/clk']), "
                    "li:has(a[href*='/pagead/'])"
                )

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        link_el = await card.query_selector(
                            "a.jcs-JobTitle[href], "
                            "h2.jobTitle a[href], "
                            "a[data-jk][href], "
                            "a[href*='/rc/clk'][href], "
                            "a[href*='/pagead/'][href]"
                        )
                        if not link_el:
                            continue

                        title = clean_text(await link_el.inner_text())
                        href = await link_el.get_attribute("href")
                        job_url = absolute_url("https://www.indeed.com", href)
                        if not title or not job_url or job_url in seen_urls:
                            continue

                        company_el = await card.query_selector(
                            "[data-testid='company-name'], "
                            "span.companyName, "
                            "span[data-testid='company-name']"
                        )
                        location_el = await card.query_selector(
                            "[data-testid='text-location'], "
                            "div.companyLocation, "
                            "div[data-testid='text-location']"
                        )
                        snippet_el = await card.query_selector(
                            ".job-snippet, "
                            "[data-testid='job-snippet'], "
                            "div[class*='job-snippet']"
                        )

                        company = clean_text(await company_el.inner_text()) if company_el else ""
                        location = clean_text(await location_el.inner_text()) if location_el else ""
                        description = clean_text(await snippet_el.inner_text()) if snippet_el else ""

                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(job_url, timeout=20000, wait_until="domcontentloaded")
                            await detail_page.wait_for_timeout(1800)
                            desc_el = await detail_page.query_selector(
                                "#jobDescriptionText, "
                                "[data-testid='jobDescriptionText'], "
                                "div[class*='jobsearch-JobComponent-description']"
                            )
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id("indeed", job_url),
                            "source": "indeed",
                            "title": title,
                            "company": company,
                            "location": location,
                            "url": job_url,
                            "description": description,
                        }
                        seen_urls.add(job_url)
                        jobs.append(job)
                        if on_job:
                            on_job(job)
                    except Exception as e:
                        print(f"[Indeed] card parse error: {e}")
                        continue

                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Indeed] query error for '{query}': {e}")
            finally:
                await page.close()

        await browser.close()

    return jobs
