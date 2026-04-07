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


def title_matches(title: str) -> bool:
    """Return True if the job title contains any of the required keywords."""
    t = title.lower()
    return any(kw in t for kw in TITLE_KEYWORDS)
