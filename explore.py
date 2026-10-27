# SPDX-License-Identifier: AGPL-3.0-only
"""Library-aware discovery shelves and public list browsing.

Filters ownership, ignored titles, language, quality and release constraints before rendering recommendation rows.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import datetime
import hashlib
import math
import re
import threading
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import cult_discovery
import indexer_discovery
import popular_downloads
import release_watch
import ignored_titles
import providers
import suggestions
import taste
import trakt_features

_library_cache = {}
_library_lock = threading.Lock()


def library(settings, loader, refresh=False):
    cfg = settings.get("plex", {})
    if not cfg.get("key"):
        return [], False
    identity = hashlib.sha256(
        (cfg.get("url", "") + "\0" + cfg["key"]).encode()
    ).hexdigest()
    with _library_lock:
        saved = _library_cache.get(identity)
        if not refresh and saved and time.time() - saved[0] < 1200:
            return copy.deepcopy(saved[1]), True
        rows = loader(settings)
        _library_cache[identity] = (time.time(), rows)
        return copy.deepcopy(rows), True


def title_key(row):
    return ("tv" if row.get("type") == "show" else "movie") + ":" + str(row.get("tmdb"))


def normalized_title(title):
    return re.sub(r"\W+", "", str(title).casefold())


def ownership(catalog):
    ids, fallback = set(), set()
    for row in catalog:
        kind = row["type"]
        if row.get("ids", {}).get("tmdb"):
            ids.add(title_key({"type": kind, "tmdb": row["ids"]["tmdb"]}))
        else:
            fallback.add(
                (kind, normalized_title(row["title"]), str(row.get("year") or ""))
            )
    return (
        lambda row: title_key(row) in ids
        or (row["type"], normalized_title(row["title"]), str(row.get("year") or ""))
        in fallback
    )


def card(row, media, reason):
    date = row.get("release_date") or row.get("first_air_date") or ""
    return {
        "key": ("tv" if media == "tv" else "movie") + ":" + str(row["id"]),
        "tmdb": str(row["id"]),
        "type": "show" if media == "tv" else "movie",
        "title": row.get("title") or row.get("name") or "Untitled",
        "poster": providers.image_url(row.get("poster_path")),
        "year": date[:4],
        "release_date": date,
        "rating": row.get("vote_average"),
        "vote_count": int(row.get("vote_count") or 0),
        "original_language": row.get("original_language"),
        "genre_ids": row.get("genre_ids", []),
        "overview": row.get("overview") or "",
        "adult": bool(row.get("adult")),
        "reasons": [reason],
        "provider": "TMDB",
    }


def qualifies(row, quality="6.0", recent=False):
    rating = row.get("rating")
    votes = int(row.get("vote_count") or 0)
    minimum = float(quality)
    threshold = (
        (30 if row["type"] == "movie" else 15)
        if recent
        else (150 if row["type"] == "movie" else 50)
    )
    return (
        not row.get("adult")
        and rating is not None
        and float(rating) >= minimum
        and votes >= threshold
    )


def profile(catalog):
    weights = Counter()
    for row in catalog:
        feedback = row.get("_feedback")
        rating = row.get("user_rating") or 0
        weight = (
            6
            if feedback == "favorite"
            else (
                4
                if feedback == "like"
                else (
                    -2
                    if feedback == "dislike"
                    else (
                        -1
                        if 0 < rating < 5
                        else 4 if rating >= 8 else 2 if row.get("watched") else 0
                    )
                )
            )
        )
        for genre in set(row.get("genres") or []):
            weights[genre] += weight
    # Prefer recent watches, then recent additions. Spread seeds across movie/TV.
    ordered = sorted(
        catalog,
        key=lambda r: (
            {"favorite": 3, "like": 2}.get(r.get("_feedback"), 0),
            bool(r.get("watched")),
            r.get("last_viewed_at", 0),
            r.get("user_rating") or 0,
        ),
        reverse=True,
    )
    seeds, seen, counts = [], set(), Counter()
    for row in ordered:
        if (
            row.get("_feedback") == "dislike"
            or not row.get("_feedback")
            and (
                0 < (row.get("user_rating") or 0) < 5
                or not row.get("watched")
                and (row.get("user_rating") or 0) < 8
            )
        ):
            continue
        ids = row.get("ids") or {}
        identity = (
            row["type"],
            ids.get("tmdb") or ids.get("tvdb") or ids.get("imdb") or row["key"],
        )
        if identity in seen or counts[row["type"]] >= 3:
            continue
        seen.add(identity)
        counts[row["type"]] += 1
        seeds.append(row)
        if len(seeds) >= 6:
            break
    return (
        Counter({name: weight for name, weight in weights.items() if weight > 0}),
        seeds,
    )


def is_upcoming(row, today):
    try:
        date = datetime.date.fromisoformat((row.get("release_date") or "")[:10])
        return today < date <= today + datetime.timedelta(days=180)
    except (ValueError, TypeError):
        return False


def language_preferences(value):
    if (
        not isinstance(value, list)
        or len(value) > 50
        or any(
            not isinstance(code, str) or not re.fullmatch("[a-z]{2,3}", code)
            for code in value
        )
    ):
        raise ValueError("Choose valid original languages (up to 50).")
    return list(dict.fromkeys(value))


def tracked(item, state):
    return any(
        str(row.get("tmdb")) == str(item.get("tmdb"))
        and row.get("type", "movie") == item.get("type")
        for row in state.get("release_watchlist", [])
    )


def home(state, body, loader):
    settings = state["settings"]
    target = body.get("shelf")
    page = int(body.get("page", 1))
    if target is not None and (
        not isinstance(target, str) or not re.fullmatch(r"[a-z0-9-]{1,50}", target)
    ):
        raise ValueError("Choose a valid Explore shelf.")
    if not 1 <= page <= 167:
        raise ValueError("This shelf has reached its browsing limit.")
    next_pages = []
    country = release_watch.region(
        body.get("region", state.get("release_region", "CA"))
    )
    languages = language_preferences(state.get("explore_languages", []))
    media_filter = body.get("type", "both")
    quality = body.get("quality", "6.0")
    if media_filter not in ("both", "movie", "show") or quality not in (
        "5.0",
        "6.0",
        "7.0",
        "8.0",
        "9.0",
    ):
        raise ValueError("Choose a valid media type and quality filter.")
    warnings = []
    try:
        catalog, connected = library(settings, loader, bool(body.get("refresh")))
    except ValueError:
        catalog, connected = [], False
        warnings.append(
            "Plex is unavailable. Recommendations cannot be filtered against your library until it reconnects."
        )
    owned = ownership(catalog)
    taste_catalog = taste.catalog_with_feedback(
        catalog, state.get("taste_feedback", {})
    )
    weights, seeds = profile(
        [
            row
            for row in taste_catalog
            if not ignored_titles.matches(
                {**row, **(row.get("ids") or {})}, state.get("ignored_titles", [])
            )
        ]
    )
    media_types = (
        ["movie", "tv"]
        if media_filter == "both"
        else ["movie" if media_filter == "movie" else "tv"]
    )
    rows = []
    seen = set()

    def language_matches(item):
        if not languages:
            return True
        language = item.get("original_language")
        if not language:
            try:
                data = providers.cached_tmdb(
                    ("movie/" if item["type"] == "movie" else "tv/")
                    + str(item["tmdb"]),
                    settings,
                )
                language = data.get("original_language")
                item["original_language"] = language
            except ValueError:
                return False
        return language in languages

    def add(
        identifier, name, note, items, recent=False, exception=False, upcoming=False
    ):
        if target and identifier != target:
            return
        visible = []
        for item in items:
            if media_filter != "both" and item["type"] != media_filter:
                continue
            if (
                not language_matches(item)
                or ignored_titles.matches(item, state.get("ignored_titles", []))
                or item.get("adult")
                or tracked(item, state)
                or owned(item)
                or item["key"] in seen
                or (
                    not exception
                    and not (
                        upcoming
                        and int(item.get("vote_count") or 0)
                        < (150 if item["type"] == "movie" else 50)
                    )
                    and not qualifies(item, quality, recent)
                )
            ):
                continue
            seen.add(item["key"])
            visible.append(item)
            if not target and len(visible) == 20:
                break
        rows.append({"id": identifier, "name": name, "note": note, "items": visible})

    if not settings.get("tmdb", {}).get("key"):
        return {
            "rows": [],
            "profile": {
                "count": len(catalog),
                "watched": sum(bool(r.get("watched")) for r in catalog),
                "genres": [],
            },
            "warnings": warnings + ["Connect TMDB to discover movies and TV."],
            "library_connected": connected,
            "checked_at": time.time(),
        }

    def seed_data(seed):
        row = {
            "type": seed["type"],
            "title": seed["title"],
            **{
                p: v
                for p, v in seed.get("ids", {}).items()
                if p in ("tmdb", "tvdb", "imdb")
            },
        }
        try:
            row = providers.enrich(row, settings)
            if not row.get("tmdb"):
                return None
            return (
                seed,
                row,
                providers.cached_tmdb(
                    ("movie/" if row["type"] == "movie" else "tv/") + row["tmdb"],
                    settings,
                ),
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        resolved = [r for r in pool.map(seed_data, seeds) if r]
    if not weights:
        for seed, _, data in resolved:
            for genre in data.get("genres", []):
                weights[genre["name"]] += 3 if seed.get("watched") else 1
    top_genres = [name for name, _ in weights.most_common(5)]
    jobs = []
    today = datetime.datetime.now(datetime.timezone.utc).date()
    min_rating = float(quality)
    genre_maps = {}
    for media in media_types:
        try:
            genre_maps[media] = {
                g["name"].casefold(): str(g["id"])
                for g in providers.cached_tmdb(
                    "genre/" + media + "/list", settings
                ).get("genres", [])
            }
        except ValueError:
            genre_maps[media] = {}

    def genre_ids(name, media):
        names = {
            "sci-fi & fantasy": ["science fiction", "fantasy"],
            "science fiction": ["sci-fi & fantasy"],
            "action & adventure": ["action", "adventure"],
            "action": ["action & adventure"],
            "adventure": ["action & adventure"],
        }
        return list(
            dict.fromkeys(
                genre_maps[media][n]
                for n in [name.casefold()] + names.get(name.casefold(), [])
                if n in genre_maps[media]
            )
        )

    def query_job(identifier, name, note, media, extra, reason, recent=False):
        params = {
            "include_adult": "false",
            "vote_average.gte": min_rating,
            "vote_count.gte": (
                (30 if media == "movie" else 15)
                if recent
                else (150 if media == "movie" else 50)
            ),
            "sort_by": "popularity.desc",
            "page": 1,
            **extra,
        }
        for language in languages or [None]:
            query = dict(params)
            if language:
                query["with_original_language"] = language
            jobs.append(
                (
                    identifier,
                    name,
                    note,
                    media,
                    "discover/" + media + "?" + urllib.parse.urlencode(query),
                    reason,
                    recent,
                )
            )

    for media in media_types:
        dates = (
            {
                "primary_release_date.gte": str(today - datetime.timedelta(days=90)),
                "primary_release_date.lte": str(today),
            }
            if media == "movie"
            else {
                "first_air_date.gte": str(today - datetime.timedelta(days=90)),
                "first_air_date.lte": str(today),
            }
        )
        if media == "movie":
            for identifier, name, types in [
                ("recent-theatrical", "In theaters", "2|3"),
                ("recent-home", "Available digitally / on disc", "4|5"),
            ]:
                query_job(
                    identifier,
                    name,
                    "Regional release dates for "
                    + country
                    + ". Last 90 days; digital may mean rental or purchase. Theater listings are release records, not live showtimes.",
                    media,
                    {
                        "region": country,
                        "with_release_type": types,
                        "release_date.gte": str(today - datetime.timedelta(days=90)),
                        "release_date.lte": str(today),
                    },
                    "Recent "
                    + ("theatrical" if types == "2|3" else "home")
                    + " release",
                    True,
                )
        else:
            query_job(
                "recent-" + media,
                "New TV series",
                "Released in the last 90 days. Early ratings use a lower vote-count floor and may change.",
                media,
                dates,
                "Recently released",
                True,
            )
        if media == "tv":
            query_job(
                "recent-episodes",
                "TV with recent episodes",
                "Shows with episodes aired in the last 30 days, excluding series already in Plex.",
                media,
                {
                    "air_date.gte": str(today - datetime.timedelta(days=30)),
                    "air_date.lte": str(today),
                    "first_air_date.lte": str(today - datetime.timedelta(days=90)),
                },
                "Recent episodes",
            )
    for index, name in enumerate(top_genres[:4]):
        for media in media_types:
            ids = genre_ids(name, media)
            if ids:
                query_job(
                    "genre-" + str(index),
                    name + " for your library",
                    "Based on watched titles, high Plex ratings and explicit taste feedback.",
                    "movie" if media == "movie" else "tv",
                    {"with_genres": "|".join(ids)},
                    "More " + name,
                )
    for media in media_types:
        query_job(
            "gems",
            "Well rated, less obvious",
            "Strong ratings with a smaller audience; not a guarantee that every title is obscure.",
            media,
            {
                "sort_by": "vote_average.desc",
                "vote_count.lte": 1500,
                "vote_average.gte": max(7.3, min_rating),
            },
            "Well rated discovery",
        )
        if not resolved:
            query_job(
                "popular",
                "A good place to start",
                "Popular, better-rated picks. Connect Plex to personalize these and hide titles you own.",
                media,
                {},
                "Popular and well rated",
            )
    if target:
        jobs = [job for job in jobs if job[0] == target]

    def fetch(job):
        try:
            candidates = []
            start = (page - 1) * 3 + 1 if target else 1
            for upstream in range(start, min(start + 3, 501) if target else 6):
                path = job[4].replace("page=1", "page=" + str(upstream))
                data = providers.cached_tmdb(path, settings)
                incoming = [
                    card(r, job[3], job[5])
                    for r in data.get("results", [])
                    if str(r.get("id", "")).isdigit()
                ]
                if job[0] in ("recent-theatrical", "recent-home"):
                    verified = []
                    for item in incoming:
                        if (
                            owned(item)
                            or ignored_titles.matches(
                                item, state.get("ignored_titles", [])
                            )
                            or not qualifies(item, quality, True)
                        ):
                            continue
                        try:
                            info = release_watch.availability(
                                item["tmdb"], country, settings, today
                            )
                        except ValueError:
                            continue
                        expected = "home" if job[0] == "recent-home" else "theatrical"
                        if info["status"] == expected:
                            item["availability"] = info
                            verified.append(item)
                    incoming = verified
                candidates.extend(incoming)
                eligible = [
                    r
                    for r in candidates
                    if language_matches(r)
                    and not owned(r)
                    and not ignored_titles.matches(r, state.get("ignored_titles", []))
                    and qualifies(r, quality, job[6])
                ]
                if upstream >= data.get("total_pages", 1):
                    break
                if target and upstream == start + 2 and upstream < 500:
                    next_pages.append(True)
                if not target and len(eligible) >= 20:
                    break
            return job, candidates
        except ValueError:
            if target:
                raise
            return job, []

    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(fetch, jobs))

    # Upcoming discovery cannot rely on audience ratings that do not exist yet.
    def upcoming_candidates(media):
        if target and target != "upcoming-" + media:
            return []
        items = []
        date_key = "release_date" if media == "movie" else "first_air_date"
        for language in languages or [None]:
            start = (page - 1) * 3 + 1 if target else 1
            for upstream in range(start, min(start + 3, 501)):
                params = {
                    "include_adult": "false",
                    date_key + ".gte": str(today + datetime.timedelta(days=1)),
                    date_key + ".lte": str(today + datetime.timedelta(days=180)),
                    "sort_by": "popularity.desc",
                    "page": upstream,
                }
                if media == "movie":
                    params.update({"region": country, "with_release_type": "2|3|4|5"})
                if language:
                    params["with_original_language"] = language
                try:
                    data = providers.cached_tmdb(
                        "discover/" + media + "?" + urllib.parse.urlencode(params),
                        settings,
                    )
                except ValueError:
                    if target:
                        raise
                    break
                candidates = [
                    card(
                        r,
                        media,
                        "Expected release "
                        + (r.get("release_date") or r.get("first_air_date") or "TBA"),
                    )
                    for r in data.get("results", [])
                    if str(r.get("id", "")).isdigit()
                ]
                items.extend(
                    r
                    for r in candidates
                    if is_upcoming(r, today)
                    and language_matches(r)
                    and not owned(r)
                    and not ignored_titles.matches(r, state.get("ignored_titles", []))
                )
                if upstream >= data.get("total_pages", 1):
                    break
                if target and upstream == start + 2 and upstream < 500:
                    next_pages.append(True)
                if not target and len(items) >= 40:
                    break
        return items

    def trending_upcoming():
        if target and target != "trending-upcoming":
            return []
        items = []
        start = (page - 1) * 3 + 1 if target else 1
        for upstream in range(start, min(start + 3, 501) if target else 6):
            try:
                data = providers.cached_tmdb(
                    "trending/all/week?page=" + str(upstream), settings
                )
            except ValueError:
                if target:
                    raise
                break
            for result in data.get("results", []):
                media = result.get("media_type")
                if media not in media_types or not str(result.get("id", "")).isdigit():
                    continue
                item = card(result, media, "Trending on TMDB this week")
                if is_upcoming(item, today):
                    items.append(item)
            if upstream >= data.get("total_pages", 1):
                break
            if target and upstream == start + 2 and upstream < 500:
                next_pages.append(True)
            if not target and len(items) >= 30:
                break
        return items

    with ThreadPoolExecutor(max_workers=3) as pool:
        upcoming_jobs = {
            media: pool.submit(upcoming_candidates, media) for media in media_types
        }
        trending_job = pool.submit(trending_upcoming)
        upcoming_rows = {
            media: future.result() for media, future in upcoming_jobs.items()
        }
        trending = trending_job.result()
    upcoming_note = "Expected within the next 180 days. Dates may change; unrated/early-rated titles are exempt from the rating minimum. Existing library, ignore and language filters still apply."
    for item in trending + [r for items in upcoming_rows.values() for r in items]:
        item["upcoming"] = True
        if int(item.get("vote_count") or 0) < (150 if item["type"] == "movie" else 50):
            item["rating"] = None
    add(
        "trending-upcoming",
        "Trending upcoming",
        upcoming_note + " Weekly TMDB trends; future original release/premiere dates.",
        trending,
        upcoming=True,
    )
    for media, items in upcoming_rows.items():
        add(
            "upcoming-" + media,
            "Upcoming movies" if media == "movie" else "Upcoming TV",
            upcoming_note
            + (
                " Movie dates use " + country + "."
                if media == "movie"
                else " TV dates refer to the original series premiere, not guaranteed local availability."
            ),
            items,
            upcoming=True,
        )
    # Favorites provide explicit "because" reasons via the existing explainable engine.
    personal = []
    personal_seeds = [
        r for r in resolved if media_filter == "both" or r[1]["type"] == media_filter
    ]
    if media_filter == "both":
        mixed = [
            next((r for r in personal_seeds if r[1]["type"] == kind), None)
            for kind in ("movie", "show")
        ]
        mixed = [r for r in mixed if r]
        personal_seeds = mixed + [r for r in personal_seeds if r not in mixed]
    for seed, row, _ in personal_seeds[:3] if not target or target == "for-you" else []:
        try:
            recs = suggestions.discover(row["type"], row["tmdb"], settings)["items"]
            for rec in recs:
                evidence = (
                    "you favorited "
                    if seed.get("_feedback") == "favorite"
                    else (
                        "you liked "
                        if seed.get("_feedback") == "like"
                        else (
                            "you highly rated "
                            if (seed.get("user_rating") or 0) >= 8
                            else "you watched "
                        )
                    )
                )
                rec["reasons"] = ["Because " + evidence + seed["title"]] + rec.get(
                    "reasons", []
                )
            personal.append((seed, recs))
        except ValueError:
            warnings.append("Some personalized title matches could not be loaded.")
    if personal:
        combined = taste.rank(
            [r for _, recs in personal for r in recs], state.get("taste_feedback", {})
        )
        add(
            "for-you",
            "Picked for your library",
            "Shared filmmakers, cast, genres and story themes from watched, highly rated, liked and favorited titles. Explicit dislikes reduce personal ranking.",
            combined,
        )
    # Franchise gaps are an additional row; low-rated sequels still obey the quality filter.
    collections = {
        data["belongs_to_collection"]["id"]: data["belongs_to_collection"]
        for _, row, data in resolved
        if row["type"] == "movie" and data.get("belongs_to_collection")
    }
    gaps = []
    for identifier, collection in (
        list(collections.items())[:3] if not target or target == "gaps" else []
    ):
        try:
            parts = providers.cached_tmdb(
                "collection/" + str(identifier), settings
            ).get("parts", [])
            gaps.extend(
                card(
                    r,
                    "movie",
                    "From " + collection.get("name", "a collection in your library"),
                )
                for r in parts
                if str(r.get("id", "")).isdigit()
            )
        except ValueError:
            continue
    add(
        "gaps",
        "Better-rated gaps in your franchises",
        "Missing films from collections connected to your library, subject to the same rating filter.",
        gaps,
    )
    grouped = {}
    for job, items in fetched:
        identifier, name, note, _, _, _, recent = job
        grouped.setdefault(
            identifier, {"name": name, "note": note, "items": [], "recent": recent}
        )["items"].extend(items)
    for identifier, data in grouped.items():
        add(identifier, data["name"], data["note"], data["items"], data["recent"])
    if (
        body.get("guilty")
        and not body.get("defer_extra")
        and (not target or target == "cult")
    ):
        found, notices, more = cult_discovery.curated_candidates(
            state, catalog, page, lambda row: owned(row) or tracked(row, state)
        )
        if more:
            next_pages.append(True)
        warnings.extend(notices)
        items = []
        for candidate in found:
            item = card(
                candidate["details"],
                "movie" if candidate.get("kind", "movie") == "movie" else "tv",
                "From your personally curated enjoyable-bad list",
            )
            item["reasons"] = candidate["reasons"] + [candidate["confidence"]]
            items.append(item)
        add(
            "cult",
            "So bad it's good",
            "Your curated selection, personalized using taste and watch history. Rating minimums do not apply; ownership, ignore, tracking and language preferences still apply.",
            items,
            exception=True,
        )
    return {
        "rows": rows,
        "page": page,
        "has_more": bool(next_pages) if target else False,
        "profile": {
            "count": len(catalog),
            "watched": sum(bool(r.get("watched")) for r in catalog),
            "genres": top_genres,
            "seeds": [
                {"title": r["title"], "watched": bool(r.get("watched"))} for r in seeds
            ],
        },
        "library_connected": connected,
        "checked_at": time.time(),
        "warnings": list(dict.fromkeys(warnings)),
        "quality_note": quality
        + " / 10 minimum. Standard picks require 150 movie votes or 50 TV votes; recent releases require 30 or 15. Scores are TMDB audience ratings.",
    }


def list_source(url):
    host = urllib.parse.urlsplit(url or "").hostname or ""
    return {
        "letterboxd.com": "Letterboxd",
        "www.letterboxd.com": "Letterboxd",
        "mdblist.com": "MDBList",
        "www.mdblist.com": "MDBList",
        "imdb.com": "IMDb",
        "www.imdb.com": "IMDb",
        "trakt.tv": "Trakt",
        "www.trakt.tv": "Trakt",
        "chronocanon.com": "ChronoCanon",
    }.get(host, "Saved list")


def lists(state, body):
    query = str(body.get("query", "")).strip()[:200]
    source = body.get("source", "all")
    page = int(body.get("page", 1))
    mode = body.get("mode", "search")
    if source not in ("all", "trakt", "tmdb", "saved") or not 1 <= page <= 100:
        raise ValueError("Choose a valid list source and page.")
    result = {"lists": [], "page": page, "has_more": False, "warnings": []}
    if source in ("all", "saved") and page == 1:
        for entry in state["lists"]:
            if query and query.casefold() not in entry["name"].casefold():
                continue
            result["lists"].append(
                {
                    "name": entry["name"],
                    "description": "Saved in your workspace. Open to review missing content.",
                    "provider": list_source(entry.get("source")),
                    "owner": "Your workspace",
                    "count": len(entry["items"]),
                    "missing": sum(
                        r.get("status") in ("missing", "partial")
                        for r in entry["items"]
                    ),
                    "url": entry.get("source"),
                    "saved_id": entry["id"],
                    "likes": 0,
                }
            )
    if source in ("all", "trakt") and state["settings"].get("trakt", {}).get("key"):
        try:
            data = trakt_features.search_lists(
                state["settings"],
                query,
                "search" if query else (mode if mode != "search" else "popular"),
                page,
            )
            result["lists"].extend(dict(r, provider="Trakt") for r in data["lists"])
            result["has_more"] |= data["has_more"]
        except ValueError as exc:
            result["warnings"].append("Trakt: " + str(exc))
    if source in ("all", "tmdb") and query:
        try:
            data = providers.cached_tmdb(
                "search/collection?"
                + urllib.parse.urlencode(
                    {"query": query, "page": page, "include_adult": "false"}
                ),
                state["settings"],
            )
            result["lists"].extend(
                {
                    "name": r["name"],
                    "description": r.get("overview") or "TMDB movie collection.",
                    "provider": "TMDB collection",
                    "owner": "TMDB",
                    "collection_id": str(r["id"]),
                    "count": None,
                    "likes": 0,
                    "url": "https://www.themoviedb.org/collection/" + str(r["id"]),
                }
                for r in data.get("results", [])
            )
            result["has_more"] |= int(data.get("total_pages", 1)) > page
        except ValueError as exc:
            result["warnings"].append("TMDB: " + str(exc))
    return result


def collection(identifier, settings):
    if not str(identifier).isdigit() or int(identifier) < 1:
        raise ValueError("Choose a valid collection ID.")
    data = providers.cached_tmdb("collection/" + str(identifier), settings)
    rows = [
        {
            "type": "movie",
            "title": r.get("title") or "Untitled",
            "tmdb": str(r["id"]),
            "year": (r.get("release_date") or "")[:4],
        }
        for r in sorted(
            data.get("parts", []),
            key=lambda r: (r.get("release_date") or "9999", r["id"]),
        )
        if str(r.get("id", "")).isdigit()
    ]
    return {
        "name": data.get("name") or "Movie collection",
        "items": rows,
        "source": None,
        "collection_id": str(identifier),
    }


def extra_shelf(state, body, loader, call):
    page = int(body.get("page", 1))
    if not 1 <= page <= 167:
        raise ValueError("Choose a valid discovery page.")
    more = False
    target = body.get("shelf")
    if target not in ("cult", "indexers", "downloads_movies", "downloads_tv"):
        raise ValueError("Choose a supported optional shelf.")
    settings = state["settings"]
    warnings = []
    if not settings.get("tmdb", {}).get("key"):
        raise ValueError("Connect TMDB for exact title metadata.")
    try:
        catalog, connected = library(settings, loader)
    except ValueError:
        catalog, connected = [], False
        warnings.append("Plex unavailable; owned-title filtering could not be checked.")
    owned = ownership(catalog)
    languages = language_preferences(state.get("explore_languages", []))
    kind = body.get("type", "both")
    quality = body.get("quality", "6.0")
    if kind not in ("both", "movie", "show") or quality not in (
        "5.0",
        "6.0",
        "7.0",
        "8.0",
        "9.0",
    ):
        raise ValueError("Choose valid filters.")
    items = []
    chart = target in ("downloads_movies", "downloads_tv")
    if chart:
        found, notices = popular_downloads.candidates(
            target, settings, bool(body.get("refresh"))
        )
        for candidate in found:
            item = card(
                candidate["details"],
                "movie" if target == "downloads_movies" else "tv",
                "Public download chart",
            )
            item["in_library"] = owned(item)
            item["chart_rank"] = candidate.get("rank", len(items) + 1)
            item["reasons"] = [
                (
                    ("TorrentFreak weekly rank #" + str(candidate["rank"]))
                    if target == "downloads_movies"
                    else str(candidate["seeders"])
                    + " seeders on strongest release in recent EZTV sample"
                )
            ]
            items.append(item)
        name = "Popular downloads - " + (
            "Movies" if target == "downloads_movies" else "TV shows"
        )
        note = (
            "TorrentFreak estimated weekly movie download chart, in source order."
            if target == "downloads_movies"
            else "EZTV: up to 300 recent releases grouped by show, ranked by strongest observed seed count. A sampled ranking, not a global TV download chart."
        )
        note += " Rating and language preferences do not filter these charts. Ignored titles stay hidden."
    elif target == "cult":
        found, notices, more = cult_discovery.curated_candidates(
            state, catalog, page, lambda row: owned(row) or tracked(row, state)
        )
        for candidate in found:
            item = card(
                candidate["details"],
                "movie" if candidate.get("kind", "movie") == "movie" else "tv",
                "From your personally curated enjoyable-bad list",
            )
            item["reasons"] = candidate["reasons"] + [candidate["confidence"]]
            items.append(item)
        name = "So bad it's good"
        note = "Your curated selection, personalized using taste and watch history. Rating minimums do not apply; ownership, ignore, tracking and language preferences still apply."
    else:
        found, notices = indexer_discovery.candidates(
            settings, call, bool(body.get("refresh"))
        )
        for candidate in found:
            item = card(
                candidate["details"],
                "movie" if candidate["kind"] == "movie" else "tv",
                "Popular in your configured indexer sample",
            )
            item["reasons"] = [
                str(candidate["seeders"])
                + " seeders (strongest observed release; duplicates are not summed)",
                candidate.get("matched_by", "Provider ID"),
                "From your configured indexers, not a global chart",
            ]
            items.append(item)
        name = "Popular on your indexers"
        note = "Exact title matches ranked by observed seeders. Quality, language, ignored-title and library filters apply. Results depend on each indexer browse support."
    warnings.extend(notices)
    unique = set()
    visible = []
    excluded = {
        "already in Plex": 0,
        "ignored": 0,
        "media type": 0,
        "language": 0,
        "rating or vote count": 0,
    }
    for item in items:
        if item["key"] in unique or item.get("adult"):
            continue
        unique.add(item["key"])
        if owned(item) and (not chart or body.get("missing_only", False)):
            excluded["already in Plex"] += 1
            continue
        if ignored_titles.matches(item, state.get("ignored_titles", [])) or tracked(
            item, state
        ):
            excluded["ignored"] += 1
            continue
        if kind != "both" and kind != item["type"]:
            excluded["media type"] += 1
            continue
        if not chart and languages and item.get("original_language") not in languages:
            excluded["language"] += 1
            continue
        if not chart and target != "cult" and not qualifies(item, quality):
            excluded["rating or vote count"] += 1
            continue
        visible.append(item)
    if target == "indexers":
        warnings.append(
            str(len(visible))
            + (" title passes" if len(visible) == 1 else " titles pass")
            + " your filters. "
            + ", ".join(
                str(count) + " " + reason for reason, count in excluded.items() if count
            )
            + ("." if any(excluded.values()) else "No titles excluded.")
        )
    return {
        "rows": [
            {
                "id": target,
                "name": name,
                "note": note,
                "source_url": (
                    popular_downloads.MOVIES
                    if target == "downloads_movies"
                    else "https://eztvx.to/api/" if target == "downloads_tv" else None
                ),
                "items": visible,
            }
        ],
        "has_more": more,
        "warnings": warnings,
        "checked_at": time.time(),
    }
