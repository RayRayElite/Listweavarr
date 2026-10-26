# SPDX-License-Identifier: AGPL-3.0-only
"""Public Trakt lists, ratings, recommendations and calendars.

Uses public client identification; preserves ranked list entries and exact movie/show/episode scope.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import datetime
import hashlib
import json
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import providers


def cached_get(path, settings, ttl=3600):
    client = settings.get("trakt", {}).get("key", "")
    if not client:
        raise ValueError("Connect Trakt under Connections first.")
    folder = providers.CACHE / "trakt"
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / (
        hashlib.sha256((client + "\0" + path).encode()).hexdigest() + ".json"
    )
    if file.exists() and time.time() - file.stat().st_mtime < ttl:
        return json.loads(file.read_text("utf-8"))
    data, headers = providers.trakt_get(path, settings)
    result = {"data": data, "headers": headers}
    temp = file.with_suffix("." + str(threading.get_ident()) + ".tmp")
    temp.write_text(json.dumps(result), "utf-8")
    temp.replace(file)
    return result


def list_card(record):
    item = record.get("list", record)
    ids = item.get("ids") or {}
    owner = ((item.get("user") or {}).get("ids") or {}).get("slug")
    slug = ids.get("slug")
    if owner and slug:
        url = (
            "https://trakt.tv/users/"
            + urllib.parse.quote(owner, safe="")
            + "/lists/"
            + urllib.parse.quote(slug, safe="")
        )
    elif str(ids.get("trakt", "")).isdigit():
        url = "https://trakt.tv/lists/" + str(ids["trakt"])
    else:
        raise ValueError("Trakt returned a list without a usable identifier.")
    return {
        "name": item.get("name") or "Trakt list",
        "description": item.get("description") or "",
        "url": url,
        "owner": (item.get("user") or {}).get("username") or owner or "Trakt",
        "count": item.get("item_count"),
        "likes": item.get("likes", record.get("like_count", 0)),
        "updated_at": item.get("updated_at"),
    }


def search_lists(settings, query="", mode="search", page=1):
    page = int(page)
    if not 1 <= page <= 100:
        raise ValueError("Choose a result page from 1 to 100.")
    params = {"page": page, "limit": 20}
    if mode == "search":
        query = str(query).strip()[:200]
        if not query:
            raise ValueError("Enter a list search, such as Marvel chronological.")
        params["query"] = query
        path = "/search/list"
    elif mode in ("popular", "trending"):
        path = "/lists/" + mode
    else:
        raise ValueError("Choose search, popular, or trending lists.")
    response = cached_get(path + "?" + urllib.parse.urlencode(params), settings, 900)
    return {
        "lists": [list_card(r) for r in response["data"]],
        "page": page,
        "has_more": int(response["headers"].get("x-pagination-page-count", page))
        > page,
    }


def resolve_title(kind, tmdb, settings):
    if kind not in ("movie", "show") or not str(tmdb).isdigit():
        raise ValueError("An exact TMDB movie or show ID is required.")
    result = cached_get("/search/tmdb/" + str(tmdb) + "?type=" + kind, settings, 86400)[
        "data"
    ]
    matches = [
        r[kind]
        for r in result
        if r.get("type") == kind
        and str((r.get(kind, {}).get("ids") or {}).get("tmdb")) == str(tmdb)
    ]
    if len(matches) != 1:
        raise ValueError("Trakt could not identify this exact title.")
    return matches[0]


def title_lists(settings, body):
    kind = body.get("type", "movie")
    if kind not in ("movie", "show", "season", "episode"):
        raise ValueError("Choose a movie, show, season, or episode.")
    page = int(body.get("page", 1))
    if not 1 <= page <= 100:
        raise ValueError("Choose a result page from 1 to 100.")
    parent_kind = "movie" if kind == "movie" else "show"
    media = resolve_title(parent_kind, body.get("tmdb"), settings)
    identifier = (media.get("ids") or {}).get("trakt")
    if not str(identifier).isdigit():
        raise ValueError("Trakt returned no usable title ID.")
    base = ("/movies/" if parent_kind == "movie" else "/shows/") + str(identifier)
    response = cached_get(
        base + "/lists/personal/popular?page=" + str(page) + "&limit=5", settings
    )
    headers = response.get("headers", {})
    return {
        "lists": [list_card(r) for r in response["data"]],
        "page": page,
        "has_more": page < 100
        and (
            int(headers["x-pagination-page-count"]) > page
            if headers.get("x-pagination-page-count")
            else len(response["data"]) == 5
        ),
    }


def title_features(settings, body):
    kind = body.get("type", "movie")
    parent_kind = "movie" if kind == "movie" else "show"
    media = resolve_title(parent_kind, body.get("tmdb"), settings)
    identifier = (media.get("ids") or {}).get("trakt")
    if not str(identifier).isdigit():
        raise ValueError("Trakt returned no usable title ID.")
    base = ("/movies/" if parent_kind == "movie" else "/shows/") + str(identifier)
    rating_path = base
    if kind in ("episode", "season"):
        season = str(body.get("season", ""))
        episode = str(body.get("episode", ""))
        if not season.isdigit() or (kind == "episode" and not episode.isdigit()):
            raise ValueError("Exact TV season/episode numbers are required.")
        rating_path += "/seasons/" + season
        if kind == "episode":
            rating_path += "/episodes/" + episode
    rating = cached_get(rating_path + "/ratings", settings, 21600)["data"]
    lists = title_lists(settings, {**body, "page": 1})
    related = cached_get(base + "/related?page=1&limit=8", settings)["data"]
    recommendations = []
    for r in related:
        ids = r.get("ids") or {}
        if ids.get("tmdb"):
            recommendations.append(
                {
                    "type": parent_kind,
                    "tmdb": str(ids["tmdb"]),
                    "title": r.get("title"),
                    "year": r.get("year"),
                }
            )

    # Lightweight exact-ID artwork lookups, independent of Plex coverage or full credits.
    def artwork(row):
        if settings.get("tmdb", {}).get("key"):
            try:
                data = providers.tmdb(
                    ("movie/" if row["type"] == "movie" else "tv/") + row["tmdb"],
                    settings,
                )
                row["poster"] = providers.image_url(data.get("poster_path"))
            except ValueError:
                pass
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        recommendations = list(pool.map(artwork, recommendations))
    return {
        "rating": rating.get("rating") if rating.get("votes") else None,
        "votes": rating.get("votes", 0),
        "lists": lists["lists"],
        "list_page": 1,
        "lists_has_more": lists["has_more"],
        "recommendations": recommendations,
        "scope": (
            "movie"
            if kind == "movie"
            else "parent show" if kind in ("season", "episode") else "show"
        ),
    }


def source_base(url):
    parsed = providers.validate_url(url)
    if parsed.hostname.replace("www.", "") != "trakt.tv":
        raise ValueError("Following updates is currently available for Trakt lists.")
    match = re.fullmatch(r"/users/([^/]+)/lists/([^/]+)/?", parsed.path)
    if match:
        return (
            "/users/"
            + urllib.parse.quote(urllib.parse.unquote(match[1]), safe="")
            + "/lists/"
            + urllib.parse.quote(urllib.parse.unquote(match[2]), safe="")
        )
    match = re.fullmatch(r"/lists/(\d+)/?", parsed.path)
    if match:
        return "/lists/" + match[1]
    raise ValueError("Choose a supported public Trakt list.")


def check_source(entry, settings):
    metadata, _ = providers.trakt_get(source_base(entry["source"]), settings)
    version = metadata.get("updated_at")
    baseline = entry.get("source_version")
    changed = metadata.get("item_count") != len(entry["items"]) or bool(
        baseline and version != baseline
    )
    if not baseline and version:
        try:
            changed |= datetime.datetime.fromisoformat(
                version.replace("Z", "+00:00")
            ).timestamp() > entry.get("updated_at", 0)
        except ValueError:
            pass
    return {
        "checked_at": time.time(),
        "changed": changed,
        "source_version": version,
        "count": metadata.get("item_count"),
        "saved_count": len(entry["items"]),
    }


def calendar(settings, lists):
    movie_ids, show_ids = set(), set()
    for entry in lists:
        if not entry.get(
            "followed", bool(entry.get("source") and "trakt.tv/" in entry["source"])
        ):
            continue
        for item in entry["items"]:
            if item["type"] == "movie" and item.get("tmdb"):
                movie_ids.add(str(item["tmdb"]))
            elif item["type"] != "movie":
                identifier = (
                    item.get("tmdb")
                    if item["type"] == "show"
                    else item.get("show_tmdb")
                )
                if identifier:
                    show_ids.add(str(identifier))
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now.date() - datetime.timedelta(days=1)).isoformat()
    end = now + datetime.timedelta(days=7)
    results = []
    for kind, wanted in [("movie", movie_ids), ("show", show_ids)]:
        if not wanted:
            continue
        path = (
            "/calendars/all/"
            + ("movies" if kind == "movie" else "shows")
            + "/"
            + start
            + "/9"
        )
        records = cached_get(path, settings, 3600)["data"]
        for index, record in enumerate(records):
            media = record.get(kind) or {}
            if str((media.get("ids") or {}).get("tmdb")) not in wanted:
                continue
            date = (
                record.get("first_aired") if kind == "show" else record.get("released")
            )
            if not date:
                continue
            if kind == "show":
                released = datetime.datetime.fromisoformat(date.replace("Z", "+00:00"))
                if not now <= released <= end:
                    continue
                payload = {
                    "type": "episode",
                    "show": media,
                    "episode": record.get("episode") or {},
                }
            else:
                if (
                    not now.date()
                    <= datetime.date.fromisoformat(date[:10])
                    <= end.date()
                ):
                    continue
                payload = {"type": "movie", "movie": media}
            payload["id"] = index + 1
            row = providers.trakt_row(payload)
            row.update(
                release_date=date,
                show_title=media.get("title") if kind == "show" else None,
            )
            results.append(row)
    # Reuse title artwork when cached; fetch only unique parents, concurrently.
    identities = {
        (
            row.get("type") == "movie",
            str(
                row.get("tmdb") if row.get("type") == "movie" else row.get("show_tmdb")
            ),
        )
        for row in results
    }

    def artwork(identity):
        movie, identifier = identity
        path = ("movie/" if movie else "tv/") + identifier
        data = providers.peek_tmdb(path) or providers.peek_tmdb(
            path
            + "?append_to_response=videos,credits,external_ids"
            + ("" if movie else ",aggregate_credits")
        )
        if not data and settings.get("tmdb", {}).get("key"):
            try:
                data = providers.cached_tmdb(path, settings)
            except ValueError:
                data = {}
        return identity, providers.image_url(data.get("poster_path"))

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        posters = dict(pool.map(artwork, identities))
    for row in results:
        row["poster"] = posters.get(
            (
                row.get("type") == "movie",
                str(
                    row.get("tmdb")
                    if row.get("type") == "movie"
                    else row.get("show_tmdb")
                ),
            )
        )
    unique = {}
    for row in results:
        key = (
            row["type"],
            row.get("tmdb"),
            row.get("show_tmdb"),
            row.get("season"),
            row.get("episode"),
            row["release_date"][:10],
        )
        unique[key] = row
    return {
        "items": sorted(unique.values(), key=lambda r: r["release_date"]),
        "days": 7,
        "note": "Upcoming releases for titles in your followed saved lists. Dates depend on Trakt; calendar times are shown in your browser time zone.",
    }
