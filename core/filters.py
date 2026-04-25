"""
filters.py — Job title keyword filter and match threshold.
"""

MATCH_THRESHOLD = 0.75


def title_matches(title: str, keywords: list = None) -> bool:
    """
    Return True if the job title contains any of the required keywords.

    Args:
        title: job title string
        keywords: list of keywords to match; returns True (match all) if None or empty
    """
    if not keywords:
        return True
    t = title.lower()
    return any(kw.lower() in t for kw in keywords)
