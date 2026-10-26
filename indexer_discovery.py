# SPDX-License-Identifier: AGPL-3.0-only
"""Optional read-only Prowlarr popularity observations.

Indexer browse support varies; observed release activity is a discovery signal, not global torrent popularity.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import hashlib
import datetime
import re
import unicodedata
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import providers

_cache = {}
_lock = threading.Lock()


def identity(record):
    categories = [
        int(r.get("id", 0))
        for r in (record.get("categories") or [])
        if isinstance(r, dict) and str(r.get("id", 0)).isdigit()
    ]
    movie = any(2000 <= n < 3000 for n in categories)
    tv = any(5000 <= n < 6000 for n in categories)
    if movie == tv:
        return None
    return "movie" if movie else "show"


def normalized(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(value)).casefold() if c.isalnum()
    )


def release_title(record):
    """Extract search text conservatively; it is never itself an accepted match."""
    text = str(record.get("title") or "")[:500]
    text = re.sub(r"^\[[^]]+\]\s*", "", text)
    text = re.sub(
        r"^(?:www\.)?[A-Za-z0-9_.-]+\.(?:com|net|org)\s*[- ]+", "", text, flags=re.I
    )
    scope = re.search(
        r"(?i)(?:[ ._-]|^)(?:s\d{1,3}(?:e\d{1,4})?|\d{1,2}x\d{1,3})(?=[ ._-]|$)", text
    )
    technical = re.search(
        r"(?i)[ ._-](?:\d{3,4}p|web[- .]?dl|webrip|hdtv|bluray|bdrip|remux|x26[45]|hevc)",
        text,
    )
    boundary = min(
        scope.start() if scope else len(text),
        technical.start() if technical else len(text),
    )
    years = [
        match
        for match in re.finditer(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)", text)
        if match.start() < boundary
        and 1870 <= int(match[1]) <= datetime.date.today().year + 2
    ]
    year = years[-1] if years else None
    kind = identity(record)
    if scope:
        kind = "show"
    if not kind and year and not scope:
        kind = "mixed"
    if not kind:
        return None
    cut = scope.start() if scope else len(text)
    candidate_year = None
    if year and year.start() < cut:
        cut = year.start()
        candidate_year = year[1]
    if kind in ("movie", "mixed") and not candidate_year:
        return None
    if kind == "show" and not scope:
        # TV categories can carry daily releases or season packs; remove known technical suffixes.
        technical = re.search(
            r"(?i)[ ._-](?:\d{3,4}p|web[- .]?dl|webrip|hdtv|bluray|complete|season\s*\d+)",
            text,
        )
        if technical:
            cut = min(cut, technical.start())
        if year and re.match(r"[ ._-]\d{2}[ ._-]\d{2}", text[year.end() :]):
            candidate_year = None
    title = text[:cut].replace(".", " ").replace("_", " ").strip(" -[({")
    title = re.sub(r"\s+", " ", title)
    if len(title) < 2:
        return None
    return kind, title, candidate_year


def resolve_search(record, settings):
    parsed = release_title(record)
    if not parsed:
        return None
    kind, title, year = parsed
    query = {"query": title, "include_adult": "false"}
    if year and kind != "mixed":
        query["year" if kind == "movie" else "first_air_date_year"] = year
    found = providers.cached_tmdb(
        "search/"
        + ("multi" if kind == "mixed" else "movie" if kind == "movie" else "tv")
        + "?"
        + urllib.parse.urlencode(query),
        settings,
    )
    if found.get("total_results", len(found.get("results", []))) > 20:
        return None
    matches = []
    for result in found.get("results", []):
        candidate_kind = (
            (
                "movie"
                if result.get("media_type") == "movie"
                else "show" if result.get("media_type") == "tv" else None
            )
            if kind == "mixed"
            else kind
        )
        if not candidate_kind:
            continue
        names = (
            (result.get("title"), result.get("original_title"))
            if candidate_kind == "movie"
            else (result.get("name"), result.get("original_name"))
        )
        date = (
            result.get("release_date")
            if candidate_kind == "movie"
            else result.get("first_air_date")
        )
        if not any(normalized(name) == normalized(title) for name in names if name):
            continue
        if year and str(date or "")[:4] != year:
            continue
        if not result.get("adult"):
            matches.append((candidate_kind, result["id"]))
    unique = set(matches)
    if len(unique) != 1:
        return None
    return next(iter(unique))


def candidates(settings, call, refresh=False):
    cfg = settings.get("prowlarr", {})
    if not cfg.get("key") or not cfg.get("url"):
        return [], [
            "Connect optional Prowlarr in Settings to enable indexer discovery."
        ]
    cache_key = hashlib.sha256(
        (
            cfg["url"]
            + "\0"
            + cfg["key"]
            + "\0"
            + settings.get("tmdb", {}).get("key", "")
        ).encode()
    ).hexdigest()
    with _lock:
        saved = _cache.get(cache_key)
    if saved and not refresh and time.time() - saved[0] < 1200:
        return copy.deepcopy(saved[1]), list(saved[2])
    query = urllib.parse.urlencode(
        [
            ("type", "search"),
            ("categories", "2000"),
            ("categories", "5000"),
            ("limit", "100"),
        ]
    )
    data = call(cfg["url"], "/api/v1/search?" + query, cfg["key"], timeout=20)
    if not isinstance(data, list):
        raise ValueError("Prowlarr did not return search results.")
    # Deduplicate release variants before the bounded metadata lookup pool. Keep the strongest swarm observation.
    ordered = sorted(
        [
            r
            for r in data
            if isinstance(r, dict)
            and str(r.get("seeders") or 0).isdigit()
            and int(r.get("seeders") or 0) > 0
        ],
        key=lambda r: -(int(r.get("seeders") or 0)),
    )
    shortlist = []
    release_keys = set()
    for record in ordered:
        parsed = release_title(record)
        key = (
            (identity(record), "tmdb", str(record["tmdbId"]))
            if record.get("tmdbId")
            else (
                ("imdb", str(record["imdbId"]))
                if record.get("imdbId")
                else (
                    ("title", parsed[0], normalized(parsed[1]), parsed[2])
                    if parsed
                    else None
                )
            )
        )
        if key is None or key in release_keys:
            continue
        release_keys.add(key)
        shortlist.append(record)
        if len(shortlist) >= 160:
            break

    def resolve(record):
        kind = identity(record)
        identifier = record.get("tmdbId")
        matched_by = "Provider ID"
        imdb = str(record.get("imdbId") or "")
        if imdb and not imdb.startswith("tt") and imdb.isdigit():
            imdb = "tt" + imdb.zfill(7)
        if not identifier and re.fullmatch(r"tt\d{5,10}", imdb):
            found = providers.cached_tmdb(
                "find/" + imdb + "?external_source=imdb_id", settings
            )
            matches = [
                (media, row["id"])
                for media, key in [("movie", "movie_results"), ("show", "tv_results")]
                for row in found.get(key, [])
                if not kind or kind == media
            ]
            if len(matches) == 1:
                kind, identifier = matches[0]
        if not identifier or not kind:
            matched = resolve_search(record, settings)
            if not matched:
                return None
            kind, identifier = matched
            matched_by = "Unique exact title" + (
                " and year" if release_title(record)[2] else ""
            )
        if not str(identifier).isdigit():
            return None
        details = providers.cached_tmdb(
            ("movie/" if kind == "movie" else "tv/") + str(identifier), settings
        )
        if details.get("adult"):
            return None
        return {
            "kind": kind,
            "details": details,
            "seeders": int(record.get("seeders") or 0),
            "published": record.get("publishDate"),
            "matched_by": matched_by,
        }

    def safe(record):
        try:
            return resolve(record)
        except (ValueError, TypeError):
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        resolved = [r for r in pool.map(safe, shortlist) if r]
    unique = {}
    for row in resolved:
        key = (row["kind"], str(row["details"]["id"]))
        if key not in unique:
            unique[key] = row
    result = list(unique.values())
    warnings = [
        str(len(data))
        + " releases returned; "
        + str(len(shortlist))
        + " unique candidates checked; "
        + str(len(result))
        + " titles confidently matched.",
        "Popularity reflects seed counts in this bounded sample from your indexers; it is not a worldwide chart. Indexers without browse/empty-search support may return no results.",
    ]
    if not result:
        warnings.append(
            "No exact, seeded movie/TV matches were returned. Unmatched releases are omitted rather than guessed."
        )
    with _lock:
        _cache[cache_key] = (time.time(), result, warnings)
    return copy.deepcopy(result), warnings
