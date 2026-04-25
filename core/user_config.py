import json
import os
from pathlib import Path
from typing import Dict, List

CONFIG_FILE = Path(__file__).parent.parent / "data" / "user_config.json"

DEFAULT_CONFIG = {
    "roles": [],
    "locations": [],
    "remote_ok": True,
    "cv_text": "",
    "match_threshold": 0.75,
    "enabled_scrapers": ["linkedin", "stepstone", "xing"],
}


def load_config() -> Dict:
    """Load user config from data/user_config.json, fall back to defaults."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: failed to load {CONFIG_FILE}: {e}. Using defaults.")
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(data: Dict) -> None:
    """Save user config to data/user_config.json."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_scraper_queries(
    roles: List[str],
    locations: List[str],
    key_role: str = "keywords",
    key_loc: str = "location",
) -> List[Dict[str, str]]:
    """
    Build a cross-product of roles × locations in scraper query format.

    Args:
        roles: list of role keywords
        locations: list of location strings
        key_role: dict key name for role (e.g., "keywords", "q")
        key_loc: dict key name for location (e.g., "location", "where")

    Returns:
        list of {key_role: role, key_loc: location} dicts
    """
    if not roles or not locations:
        return []

    queries = []
    for role in roles:
        for location in locations:
            queries.append({
                key_role: role,
                key_loc: location,
            })
    return queries
