"""
filters.py — Job title and description keyword filters.
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
    clean_keywords = [kw.strip().lower() for kw in keywords if kw and kw.strip()]
    if not clean_keywords:
        return True
    t = title.lower()
    return any(kw in t for kw in clean_keywords)


def description_matches(description: str, keywords: list = None) -> bool:
    """
    Return True if the job description contains any of the required keywords.

    Args:
        description: job description string
        keywords: list of keywords or phrases to match; returns True if None or empty
    """
    if not keywords:
        return True
    clean_keywords = [kw.strip().lower() for kw in keywords if kw and kw.strip()]
    if not clean_keywords:
        return True
    d = (description or "").lower()
    return any(kw in d for kw in clean_keywords)
