"""
glassdoor.py — Glassdoor job scraper via Playwright.
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


BASE_URL = "https://www.glassdoor.com/Job/jobs.htm"


async def scrape_glassdoor(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrape Glassdoor search results.
    """
    if not roles or not locations:
        print("[Glassdoor] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Glassdoor] playwright not installed.")
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
                    f"{BASE_URL}?sc.keyword={quote_query(query['q'])}"
                    f"&locKeyword={quote_query(query['l'])}"
                    "&fromAge=14"
                )
                await page.goto(url, timeout=35000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                await accept_common_cookie_banners(page)

                for _ in range(2):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1200)

                cards = await page.query_selector_all(
                    "li[data-test='jobListing'], "
                    "li[data-testid='jobListing'], "
                    "div[data-test='job-card'], "
                    "div[data-testid='job-card'], "
                    "article:has(a[href*='/job-listing/']), "
                    "li:has(a[href*='/job-listing/'])"
                )

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        link_el = await card.query_selector(
                            "a[data-test='job-title'][href], "
                            "a[data-testid='job-title'][href], "
                            "a[href*='/job-listing/'][href], "
                            "a[href*='jobListing.htm'][href]"
                        )
                        if not link_el:
                            continue

                        title = clean_text(await link_el.inner_text())
                        href = await link_el.get_attribute("href")
                        job_url = absolute_url("https://www.glassdoor.com", href)
                        if not title or not job_url or job_url in seen_urls:
                            continue

                        company_el = await card.query_selector(
                            "[data-test='employer-name'], "
                            "[data-testid='employer-name'], "
                            ".EmployerProfile_compactEmployerName__LE242, "
                            "span[class*='EmployerName']"
                        )
                        location_el = await card.query_selector(
                            "[data-test='location'], "
                            "[data-testid='location'], "
                            "div[class*='JobCard_location']"
                        )
                        snippet_el = await card.query_selector(
                            "[data-test='descSnippet'], "
                            "[data-testid='descSnippet'], "
                            "div[class*='JobCard_jobDescriptionSnippet']"
                        )

                        company = clean_text(await company_el.inner_text()) if company_el else ""
                        location = clean_text(await location_el.inner_text()) if location_el else ""
                        description = clean_text(await snippet_el.inner_text()) if snippet_el else ""

                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(job_url, timeout=25000, wait_until="domcontentloaded")
                            await detail_page.wait_for_timeout(2200)
                            await accept_common_cookie_banners(detail_page)
                            desc_el = await detail_page.query_selector(
                                "[data-test='jobDescriptionContent'], "
                                "[data-testid='jobDescriptionContent'], "
                                "div[class*='JobDetails_jobDescription'], "
                                "section[class*='JobDetails']"
                            )
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id("glassdoor", job_url),
                            "source": "glassdoor",
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
                        print(f"[Glassdoor] card parse error: {e}")
                        continue

                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Glassdoor] query error for '{query}': {e}")
            finally:
                await page.close()

        await browser.close()

    return jobs
