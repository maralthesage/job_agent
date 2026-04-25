"""
weworkremotely.py — We Work Remotely scraper via Playwright.
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


BASE_URL = "https://weworkremotely.com/remote-jobs/search"


def _is_job_href(href: str) -> bool:
    if not href:
        return False
    if not href.startswith("/remote-jobs/"):
        return False
    blocked = ("/remote-jobs/new", "/remote-jobs/search", "/remote-jobs/categories")
    return not any(href.startswith(prefix) for prefix in blocked)


async def scrape_weworkremotely(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrape We Work Remotely search results.

    WWR is remote-only, so the locations argument is accepted for API consistency
    but does not alter the search URL.
    """
    if not roles:
        print("[We Work Remotely] Roles are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[We Work Remotely] playwright not installed.")
        return []

    queries = [{"term": role} for role in roles]
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
                url = f"{BASE_URL}?term={quote_query(query['term'])}"
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                await accept_common_cookie_banners(page)

                cards = await page.query_selector_all(
                    "li.new-listing-container:has(a[href^='/remote-jobs/']), "
                    "section.jobs li:not(.view-all):has(a[href^='/remote-jobs/']), "
                    "li.feature:has(a[href^='/remote-jobs/'])"
                )

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        link_el = await card.query_selector(
                            "a[href^='/remote-jobs/']:not([href*='/categories/'])"
                        )
                        if not link_el:
                            continue

                        href = await link_el.get_attribute("href")
                        if not _is_job_href(href):
                            continue
                        job_url = absolute_url("https://weworkremotely.com", href)
                        if not job_url or job_url in seen_urls:
                            continue

                        title_el = await card.query_selector(
                            ".new-listing__header__title__text, "
                            "span.title, "
                            "span[class*='title'], "
                            "h2, h3"
                        )
                        company_el = await card.query_selector(
                            ".new-listing__company-name, "
                            "span.company, "
                            "span[class*='company']"
                        )
                        region_el = await card.query_selector(
                            ".new-listing__categories__category:last-child, "
                            ".new-listing__company-headquarters, "
                            "span.region, "
                            "span[class*='region']"
                        )
                        listing_type_el = await card.query_selector(
                            "span[class*='contract'], "
                            "span[class*='full-time'], "
                            "span[class*='company'] ~ span"
                        )

                        title = clean_text(await title_el.inner_text()) if title_el else ""
                        company = clean_text(await company_el.inner_text()) if company_el else ""
                        region = clean_text(await region_el.inner_text()) if region_el else "Remote"
                        listing_type = clean_text(await listing_type_el.inner_text()) if listing_type_el else ""
                        description = listing_type

                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(job_url, timeout=22000, wait_until="domcontentloaded")
                            await detail_page.wait_for_timeout(1800)
                            title_detail = await detail_page.query_selector("h1")
                            company_detail = await detail_page.query_selector(
                                ".company-card h2, "
                                "h2.company, "
                                "a[href*='/company/']"
                            )
                            desc_el = await detail_page.query_selector(
                                ".lis-container__job__content, "
                                ".lis-container__job, "
                                ".listing-container, "
                                ".listing, "
                                "article, "
                                "main"
                            )
                            if title_detail:
                                detail_title = clean_text(await title_detail.inner_text())
                                if detail_title and "weworkremotely" not in detail_title.lower():
                                    title = detail_title
                            if company_detail and not company:
                                company = clean_text(await company_detail.inner_text())
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        if not title:
                            continue

                        job = {
                            "id": make_job_id("weworkremotely", job_url),
                            "source": "weworkremotely",
                            "title": title,
                            "company": company,
                            "location": region,
                            "url": job_url,
                            "description": description,
                        }
                        seen_urls.add(job_url)
                        jobs.append(job)
                        if on_job:
                            on_job(job)
                    except Exception as e:
                        print(f"[We Work Remotely] card parse error: {e}")
                        continue

                await asyncio.sleep(2)
            except Exception as e:
                print(f"[We Work Remotely] query error for '{query}': {e}")
            finally:
                await page.close()

        await browser.close()

    return jobs
