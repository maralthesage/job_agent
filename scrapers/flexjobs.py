"""
flexjobs.py — FlexJobs scraper via Playwright.
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
    slugify,
)


def _search_urls(role: str, location: str) -> List[str]:
    urls = [f"https://www.flexjobs.com/search?search={quote_query(role)}"]
    if location and location.lower() not in {"remote", "work from home"}:
        urls[0] += f"&location={quote_query(location)}"
    urls.append(f"https://www.flexjobs.com/remote-jobs/titles/{slugify(role)}")
    return urls


async def scrape_flexjobs(max_jobs: int = 20, on_job=None, roles: List[str] = None, locations: List[str] = None) -> List[Dict]:
    """
    Scrape FlexJobs public search/listing pages.
    """
    if not roles or not locations:
        print("[FlexJobs] Roles and locations are required. Configure them in the settings.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[FlexJobs] playwright not installed.")
        return []

    from core.user_config import build_scraper_queries
    queries = build_scraper_queries(roles, locations, key_role="search", key_loc="location")

    jobs = []
    seen_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="en-US")

        for query in queries:
            if len(jobs) >= max_jobs:
                break
            for url in _search_urls(query["search"], query.get("location", "")):
                if len(jobs) >= max_jobs:
                    break
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)
                    await accept_common_cookie_banners(page)

                    for _ in range(2):
                        await page.keyboard.press("End")
                        await page.wait_for_timeout(1200)

                    cards = await page.query_selector_all(
                        "article:has(a[href*='/gjw/']), "
                        "div:has(a[href*='/gjw/']), "
                        "li:has(a[href*='/gjw/']), "
                        "article:has(a[href*='/remote-jobs/']), "
                        "div:has(a[href*='/remote-jobs/'])"
                    )
                    if not cards:
                        cards = await page.query_selector_all(
                            "a[href*='/gjw/'], a[href*='/remote-jobs/']"
                        )

                    for card in cards:
                        if len(jobs) >= max_jobs:
                            break
                        try:
                            card_href = await card.get_attribute("href")
                            link_el = card if card_href else await card.query_selector(
                                "a[href*='/gjw/'][href], a[href*='/remote-jobs/'][href]"
                            )
                            if not link_el:
                                continue

                            href = await link_el.get_attribute("href")
                            job_url = absolute_url("https://www.flexjobs.com", href)
                            if not job_url or job_url in seen_urls:
                                continue

                            title_el = await card.query_selector("h2, h3, h4, a[href*='/gjw/'], a[href*='/remote-jobs/']")
                            company_el = await card.query_selector(
                                "[class*='company'], "
                                "[data-testid='company'], "
                                "h3 + div"
                            )
                            location_el = await card.query_selector(
                                "[class*='location'], "
                                "[data-testid='location'], "
                                "li:has-text('Remote')"
                            )
                            snippet_el = await card.query_selector("p, [class*='description'], [class*='summary']")

                            title = clean_text(await title_el.inner_text()) if title_el else ""
                            company = clean_text(await company_el.inner_text()) if company_el else ""
                            location = clean_text(await location_el.inner_text()) if location_el else query.get("location", "")
                            description = clean_text(await snippet_el.inner_text()) if snippet_el else ""

                            try:
                                detail_page = await context.new_page()
                                await detail_page.goto(job_url, timeout=22000, wait_until="domcontentloaded")
                                await detail_page.wait_for_timeout(2000)
                                title_detail = await detail_page.query_selector("h1")
                                company_detail = await detail_page.query_selector("h2, [class*='company']")
                                location_detail = await detail_page.query_selector(
                                    "li:has-text('Location:'), "
                                    "[class*='location']"
                                )
                                desc_el = await detail_page.query_selector(
                                    "#job-description, "
                                    "[class*='job-description'], "
                                    "section:has-text('Job Description'), "
                                    "main"
                                )
                                if title_detail:
                                    title = clean_text(await title_detail.inner_text()) or title
                                if company_detail and not company:
                                    company = clean_text(await company_detail.inner_text())
                                if location_detail and not location:
                                    location = clean_text(await location_detail.inner_text())
                                if desc_el:
                                    description = (await desc_el.inner_text()).strip()
                                await detail_page.close()
                            except Exception:
                                pass

                            if not title:
                                continue

                            job = {
                                "id": make_job_id("flexjobs", job_url),
                                "source": "flexjobs",
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
                            print(f"[FlexJobs] card parse error: {e}")
                            continue

                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[FlexJobs] query error for '{query}': {e}")
                finally:
                    await page.close()

        await browser.close()

    return jobs
