"""
built_in.py — Built In job scraper via Playwright.
"""
import asyncio
from typing import Dict, List

from scrapers.common import (
    DEFAULT_USER_AGENT,
    absolute_url,
    accept_common_cookie_banners,
    clean_text,
    make_job_id,
    slugify,
)


def _search_urls(role: str, location: str) -> List[str]:
    role_slug = slugify(role)
    location_lower = location.lower()
    if "remote" in location_lower:
        return [
            f"https://builtin.com/jobs/remote/search/{role_slug}",
            f"https://builtin.com/jobs/search/{role_slug}",
        ]
    return [
        f"https://builtin.com/jobs/search/{role_slug}",
        f"https://builtin.com/jobs/remote/search/{role_slug}",
    ]


async def scrape_built_in(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrape Built In search results.
    """
    if not roles or not locations:
        print("[Built In] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Built In] playwright not installed.")
        return []

    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="q", key_loc="location")

    jobs = []
    seen_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="en-US")

        for query in queries:
            if len(jobs) >= max_jobs:
                break
            for url in _search_urls(query["q"], query["location"]):
                if len(jobs) >= max_jobs:
                    break
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3500)
                    await accept_common_cookie_banners(page)

                    for _ in range(2):
                        await page.keyboard.press("End")
                        await page.wait_for_timeout(1200)

                    cards = await page.query_selector_all(
                        "div[data-testid='job-card'], "
                        "article:has(a[href^='/job/']), "
                        "div:has(a[href^='/job/']), "
                        "li:has(a[href^='/job/'])"
                    )

                    if not cards:
                        cards = await page.query_selector_all("a[href^='/job/']")

                    for card in cards:
                        if len(jobs) >= max_jobs:
                            break
                        try:
                            link_el = await card.query_selector("a[href^='/job/']") if not await card.get_attribute("href") else card
                            if not link_el:
                                continue

                            href = await link_el.get_attribute("href")
                            job_url = absolute_url("https://builtin.com", href)
                            if not job_url or job_url in seen_urls:
                                continue

                            title_el = await card.query_selector(
                                "h2, h3, "
                                "[data-testid='job-title'], "
                                "a[href^='/job/']"
                            )
                            company_el = await card.query_selector(
                                "[data-testid='company-name'], "
                                "[class*='company'], "
                                "a[href*='/company/']"
                            )
                            location_el = await card.query_selector(
                                "[data-testid='location'], "
                                "[class*='location']"
                            )
                            snippet_el = await card.query_selector(
                                "[data-testid='job-description'], "
                                "[class*='description'], "
                                "p"
                            )

                            title = clean_text(await title_el.inner_text()) if title_el else ""
                            company = clean_text(await company_el.inner_text()) if company_el else ""
                            location = clean_text(await location_el.inner_text()) if location_el else query["location"]
                            description = clean_text(await snippet_el.inner_text()) if snippet_el else ""

                            try:
                                detail_page = await context.new_page()
                                await detail_page.goto(job_url, timeout=22000, wait_until="domcontentloaded")
                                await detail_page.wait_for_timeout(2000)
                                title_detail = await detail_page.query_selector("h1")
                                company_detail_links = await detail_page.query_selector_all("a[href*='/company/']")
                                desc_el = await detail_page.query_selector(
                                    "[data-testid='job-description'], "
                                    "[class*='job-description'], "
                                    "section:has-text('Job Description'), "
                                    "main"
                                )
                                if title_detail:
                                    title = clean_text(await title_detail.inner_text()) or title
                                if not company:
                                    for company_detail in company_detail_links:
                                        company_text = clean_text(await company_detail.inner_text())
                                        if company_text and not company_text.lower().startswith("view "):
                                            company = company_text
                                            break
                                if desc_el:
                                    description = (await desc_el.inner_text()).strip()
                                await detail_page.close()
                            except Exception:
                                pass

                            if not title:
                                continue

                            job = {
                                "id": make_job_id("buildin", job_url),
                                "source": "buildin",
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
                            print(f"[Built In] card parse error: {e}")
                            continue

                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[Built In] query error for '{query}': {e}")
                finally:
                    await page.close()

        await browser.close()

    return jobs
