# SPDX-License-Identifier: AGPL-3.0-only
"""Official catalogue taxonomy, with compatibility for older uncategorized feeds.

Explicit curator choices win. Name rules only supply defaults for existing lists;
personal history lists are not promoted into the public catalogue.
"""
import re
import unicodedata

CATEGORIES = {
    "franchises": "Franchises",
    "top": "Top Lists",
    "curated": "Curated Lists",
}


def category(row):
    explicit = row.get("category") or row.get("official_category")
    if isinstance(explicit, str) and explicit in CATEGORIES:
        return explicit
    name = " ".join(
        re.findall(
            r"[a-z0-9]+",
            unicodedata.normalize("NFKD", str(row.get("name", ""))).casefold(),
        )
    )
    if any(
        phrase in name
        for phrase in (
            "ray recommends",
            "so bad",
            "mindfuck",
            "mind fuck",
            "christmas",
            "halloween",
        )
    ):
        return "curated"
    if re.search(r"\b(?:imdb|letterboxd|tmdb) top\b|\btop \d+\b|\bawards?\b", name):
        return "top"
    return "franchises"


def validate(value):
    if not isinstance(value, str) or value not in CATEGORIES:
        raise ValueError("Choose Franchises, Top Lists or Curated Lists.")
    return value
