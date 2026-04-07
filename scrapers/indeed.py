"""
indeed.py — Indeed.de job scraper via Playwright
Searches for data roles in NRW and remote in Germany.
"""
import asyncio
import hashlib
from typing import List, Dict


SEARCH_QUERIES = [
    {"q": "Data Scientist", "l": "Düsseldorf"},
    {"q": "Data Analyst", "l": "Düsseldorf"},
    {"q": "Analytics Engineer", "l": "Nordrhein-Westfalen"},
    {"q": "Machine Learning Engineer", "l": "Nordrhein-Westfalen"},
    {"q": "Data Scientist Remote", "l": "Deutschland"},
    {"q": "Data Analyst Remote", "l": "Deutschland"},
]

BASE_URL = "https://de.indeed.com/jobs"


def make_job_id(job_key: str) -> str:
    return "indeed_" + hashlib.md5(job_key.encode()).hexdigest()[:12]


async def scrape_indeed(max_jobs: int = 20, on_job=None) -> List[Dict]:
    """
    Scrapes Indeed.de for data science/analytics jobs.
    Returns list of job dicts.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Indeed] playwright not installed.")
        return []

    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            locale="de-DE"
        )

        for query in SEARCH_QUERIES:
            if len(jobs) >= max_jobs:
                break
            try:
                page = await context.new_page()
                params = (
                    f"?q={query['q'].replace(' ', '+')}"
                    f"&l={query['l'].replace(' ', '+')}"
                    f"&sort=date"
                    f"&fromage=14"  # last 14 days
                )
                await page.goto(BASE_URL + params, timeout=30000)
                await page.wait_for_timeout(3000)

                # Dismiss cookie banner if present
                try:
                    cookie_btn = await page.query_selector("[id*='cookie'] button, .cookieConsent button")
                    if cookie_btn:
                        await cookie_btn.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

                cards = await page.query_selector_all(".job_seen_beacon, .tapItem")

                for card in cards[:8]:
                    try:
                        title_el = await card.query_selector("h2.jobTitle span[title], h2.jobTitle a")
                        company_el = await card.query_selector("[data-testid='company-name'], .companyName")
                        location_el = await card.query_selector("[data-testid='text-location'], .companyLocation")
                        link_el = await card.query_selector("h2.jobTitle a")

                        title = (await title_el.inner_text()).strip() if title_el else ""
                        company = (await company_el.inner_text()).strip() if company_el else ""
                        location = (await location_el.inner_text()).strip() if location_el else ""
                        href = await link_el.get_attribute("href") if link_el else ""
                        url = f"https://de.indeed.com{href}" if href and href.startswith("/") else href

                        if not title:
                            continue

                        # Fetch job description
                        description = ""
                        try:
                            detail_page = await context.new_page()
                            await detail_page.goto(url, timeout=20000)
                            await detail_page.wait_for_timeout(2000)
                            desc_el = await detail_page.query_selector(
                                "#jobDescriptionText, .jobsearch-JobComponent-description"
                            )
                            if desc_el:
                                description = (await desc_el.inner_text()).strip()
                            await detail_page.close()
                        except Exception:
                            pass

                        job = {
                            "id": make_job_id(title + company + location),
                            "source": "indeed",
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
                        print(f"[Indeed] card parse error: {e}")
                        continue

                await page.close()
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[Indeed] query error: {e}")
                continue

        await browser.close()

    return jobs
