"""
monster.py — Monster job scraper via Playwright.
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


BASE_URL = "https://www.monster.com/jobs/search"


async def scrape_monster(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrape Monster search results.
    """
    if not roles or not locations:
        print("[Monster] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Monster] playwright not installed.")
        return []

    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="q", key_loc="where")

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
                url = f"{BASE_URL}?q={quote_query(query['q'])}&where={quote_query(query['where'])}"
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                await accept_common_cookie_banners(page)
                body_text = ""
                try:
                    body_text = await page.locator("body").inner_text(timeout=3000)
                except Exception:
                    pass
                if not body_text.strip():
                    print("[Monster] returned an empty page; skipping query")
                    continue

                for _ in range(2):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1200)

                cards = await page.query_selector_all(
                    "article[data-testid='JobCard'], "
                    "section.card-content, "
                    "div[data-testid='job-card'], "
                    "div:has(a[href*='/job-openings/']), "
                    "li:has(a[href*='/job-openings/'])"
                )

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        link_el = await card.query_selector(
                            "a[data-testid='jobTitle'][href], "
                            "h2 a[href], h3 a[href], "
                            "a[href*='/job-openings/'][href]"
                        )
                        if not link_el:
                            continue

                        title = clean_text(await link_el.inner_text())
                        href = await link_el.get_attribute("href")
                        job_url = absolute_url("https://www.monster.com", href)
                        if not title or not job_url or job_url in seen_urls:
                            continue

                        company_el = await card.query_selector(
                            "[data-testid='company'], "
                            "[data-testid='companyName'], "
                            ".company, "
                            "span[class*='company']"
                        )
                        location_el = await card.query_selector(
                            "[data-testid='jobDetailLocation'], "
                            "[data-testid='location'], "
                            ".location, "
                            "span[class*='location']"
                        )
                        snippet_el = await card.query_selector(
                            "[data-testid='jobDescription'], "
                            ".summary, "
                            "div[class*='description']"
                        )

                        company = clean_text(await company_el.inner_text()) if company_el else ""
                        location = clean_text(await location_el.inner_text()) if location_el else ""
                        description = clean_text(await snippet_el.inner_text()) if snippet_el else ""

                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(job_url, timeout=22000, wait_until="domcontentloaded")
                            await detail_page.wait_for_timeout(2000)
                            desc_el = await detail_page.query_selector(
                                "[data-testid='jobDescription'], "
                                "[data-testid='job-description'], "
                                ".job-description, "
                                "section[class*='description'], "
                                "main"
                            )
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id("monster", job_url),
                            "source": "monster",
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
                        print(f"[Monster] card parse error: {e}")
                        continue

                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Monster] query error for '{query}': {e}")
            finally:
                await page.close()

        await browser.close()

    return jobs
