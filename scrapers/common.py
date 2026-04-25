"""
Shared helpers for Playwright-based job board scrapers.
"""
import hashlib
import re
from typing import Dict, List
from urllib.parse import quote_plus, urljoin


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def make_job_id(source: str, url: str) -> str:
    return f"{source}_" + hashlib.md5(url.encode()).hexdigest()[:12]


def quote_query(value: str) -> str:
    return quote_plus(value.strip())


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def absolute_url(base_url: str, href: str) -> str:
    if not href:
        return ""
    return urljoin(base_url, href)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def dedupe_jobs(jobs: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for job in jobs:
        url = job.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(job)
    return unique


async def accept_common_cookie_banners(page):
    selectors = (
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
        "button[data-testid='cookie-accept-button']",
        "button[data-testid='consent-accept-btn']",
        "button[id*='accept']",
        "button[class*='accept']",
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Alle akzeptieren')",
        "button:has-text('I accept')",
    )
    for selector in selectors:
        try:
            button = await page.query_selector(selector)
            if button:
                await button.click(timeout=1500)
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue
