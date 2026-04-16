"""
filters.py — Job title keyword filter and match threshold.
Single source of truth used by scraping, scoring, and display.
"""

MATCH_THRESHOLD = 0.75

TITLE_KEYWORDS = [
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "machine learning expert",
    "ai engineer",
    "data engineer",
    "data warehouse engineer",
]


def title_matches(title: str, keywords: list = None) -> bool:
    """
    Return True if the job title contains any of the required keywords.

    Args:
        title: job title string
        keywords: optional list of keywords to match; uses TITLE_KEYWORDS if not provided
    """
    t = title.lower()
    kws = keywords if keywords is not None else TITLE_KEYWORDS
    return any(kw.lower() in t for kw in kws)
