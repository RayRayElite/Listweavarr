# SPDX-License-Identifier: AGPL-3.0-only
"""A read-only calendar of releases from the user's existing follows.

Cached metadata renders immediately. Explicit refreshes use bounded provider
reads; unknown dates stay unknown. A release date never means Plex availability
or authorizes a download. Movie home dates remain regional and format-specific.
"""
import calendar
import datetime
import hashlib
import re
import time
import json
import threading
import providers
import ignored_titles
import release_watch
import trakt_features


_trakt_cache = {}
_cache_lock = threading.Lock()


def month_window(value=None, today=None):
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    value = value or today.strftime("%Y-%m")
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("Choose a calendar month in YYYY-MM format.")
    try:
        start = datetime.date.fromisoformat(value + "-01")
    except ValueError:
        raise ValueError("Choose a valid calendar month.") from None
    if abs((start.year - today.year) * 12 + start.month - today.month) > 24:
        raise ValueError("Choose a month within two years of today.")
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def build(state, month=None, refresh=False, today=None):
    start, end = month_window(month, today)
    settings = state.get("settings", {})
    country = release_watch.region(state.get("release_region", "CA"))
    # The release watchlist already records the user's selected country.
    warnings, events, memo = [], {}, {}
    budget = 50
    exhausted = False
    remote_failed = False
    missing_paths = set()

    def metadata(path):
        nonlocal budget, exhausted, remote_failed
        if path in memo:
            return memo[path]
        cached = providers.peek_tmdb(path)
        if refresh and not remote_failed and settings.get("tmdb", {}).get("key"):
            if budget > 0:
                budget -= 1
                try:
                    cached = providers.cached_tmdb(path, settings)
                except ValueError:
                    remote_failed = True
                    if (
                        "Some TMDB dates could not be refreshed; cached dates are retained."
                        not in warnings
                    ):
                        warnings.append(
                            "Some TMDB dates could not be refreshed; cached dates are retained."
                        )
            else:
                exhausted = True
        if not cached:
            missing_paths.add(path)
        memo[path] = cached
        return cached

    def add(item, value, kind, source, region=None, note=""):
        if ignored_titles.matches(item, state.get("ignored_titles", [])):
            return
        try:
            date = datetime.date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return
        if not start <= date <= end:
            return
        media = item.get("type", "movie")
        ident = item.get("show_tmdb") if media == "episode" else item.get("tmdb")
        if not ident or not str(ident).isdigit():
            return
        key = (
            media,
            str(ident),
            str(item.get("season", "")),
            str(item.get("episode", "")),
            str(date),
            kind,
            region,
        )
        if key not in events:
            events[key] = {
                "id": hashlib.sha256(repr(key).encode()).hexdigest()[:24],
                "date": str(date),
                "release_kind": kind,
                "region": region,
                "note": note,
                "sources": [],
                "item": {
                    k: item[k]
                    for k in (
                        "type",
                        "tmdb",
                        "show_tmdb",
                        "title",
                        "show_title",
                        "season",
                        "episode",
                        "poster",
                        "year",
                    )
                    if item.get(k) is not None
                },
            }
        if source not in events[key]["sources"]:
            events[key]["sources"].append(source)

    def title_events(item, source, region=None):
        kind = item.get("type", "movie")
        ident = (
            item.get("show_tmdb") if kind in ("episode", "season") else item.get("tmdb")
        )
        if not ident or not str(ident).isdigit():
            return
        data = metadata(("movie/" if kind == "movie" else "tv/") + str(ident))
        item = dict(item)
        item["poster"] = item.get("poster") or providers.image_url(
            data.get("poster_path")
        )
        if kind == "movie":
            dates = metadata("movie/" + str(ident) + "/release_dates")
            regional = next(
                (
                    r.get("release_dates", [])
                    for r in dates.get("results", [])
                    if r.get("iso_3166_1") == (region or country)
                ),
                [],
            )
            found = False
            for record in regional:
                label = {2: "theatrical", 3: "theatrical", 4: "digital", 5: "disc"}.get(
                    record.get("type")
                )
                if label:
                    found = True
                    add(
                        item,
                        record.get("release_date"),
                        label,
                        source,
                        region or country,
                    )
            if not found:
                add(
                    item,
                    data.get("release_date") or item.get("release_date"),
                    "expected",
                    source,
                    note="General movie release date; digital/disc availability is not confirmed.",
                )
            return found
        elif kind == "show":
            add(
                item,
                data.get("first_air_date") or item.get("premiere_date"),
                "premiere",
                source,
                note="Original series premiere; local service availability may differ.",
            )
            upcoming = data.get("next_episode_to_air") or {}
            if (
                upcoming.get("season_number") is not None
                and upcoming.get("episode_number") is not None
            ):
                add(
                    {
                        "type": "episode",
                        "show_tmdb": str(ident),
                        "show_title": item["title"],
                        "title": upcoming.get("name") or "Upcoming episode",
                        "season": upcoming["season_number"],
                        "episode": upcoming["episode_number"],
                        "poster": item.get("poster"),
                    },
                    upcoming.get("air_date"),
                    "episode",
                    source,
                )
            return bool(data.get("first_air_date"))
        elif kind in ("season", "episode") and str(item.get("season", "")).isdigit():
            season = metadata("tv/" + str(ident) + "/season/" + str(item["season"]))
            for episode in season.get("episodes", []):
                if kind == "episode" and str(episode.get("episode_number")) != str(
                    item.get("episode")
                ):
                    continue
                add(
                    {
                        "type": "episode",
                        "show_tmdb": str(ident),
                        "show_title": item.get("show_title")
                        or data.get("name")
                        or item["title"],
                        "title": episode.get("name") or item["title"],
                        "season": item["season"],
                        "episode": episode.get("episode_number"),
                        "poster": item.get("poster"),
                    },
                    episode.get("air_date"),
                    "episode",
                    source,
                )

    # Prioritize deliberately tracked releases before larger followed lists.
    for row in state.get("release_watchlist", []):
        source = {"type": "watchlist", "name": "Release watchlist"}
        item = dict(row, type=row.get("type", "movie"))
        known = title_events(item, source, row.get("region"))
        if not known:
            for key, kind in (
                ("theatrical_date", "theatrical"),
                ("digital_date", "digital"),
                ("disc_date", "disc"),
                ("premiere_date", "premiere"),
            ):
                add(
                    item,
                    row.get(key),
                    kind,
                    source,
                    row.get("region") if item["type"] == "movie" else None,
                )

    follows = {str(r["id"]): r for r in state.get("creator_follows", [])}
    for person in list(follows.values())[:30]:
        credits = metadata("person/" + str(person["id"]) + "/combined_credits")
        rows = (
            credits.get("cast", [])
            if person.get("role", "all") in ("cast", "all")
            else []
        ) + (
            credits.get("crew", [])
            if person.get("role", "all") in ("crew", "all")
            else []
        )
        for raw in rows:
            if raw.get("adult") or raw.get("media_type") not in ("movie", "tv"):
                continue
            date = raw.get("release_date") or raw.get("first_air_date")
            if not date or not str(start) <= date[:10] <= str(end):
                continue
            item = {
                "type": "movie" if raw["media_type"] == "movie" else "show",
                "tmdb": str(raw.get("id", "")),
                "title": raw.get("title") or raw.get("name") or "Untitled",
                "poster": providers.image_url(raw.get("poster_path")),
                "release_date": date,
            }
            source = {
                "type": "creators",
                "name": person["name"],
                "person_id": person["id"],
            }
            if item["type"] == "movie":
                title_events(item, source)
            else:
                add(item, date, "premiere", source)

    followed = []
    for entry in state.get("lists", []):
        if not entry.get(
            "followed",
            bool(entry.get("source") and "trakt.tv/" in str(entry["source"])),
        ):
            continue
        followed.append(entry)
        source = {"type": "followed", "name": entry["name"], "list_id": entry["id"]}
        seen = set()
        for item in entry.get("items", []):
            key = (
                item.get("type"),
                str(item.get("tmdb") or item.get("show_tmdb")),
                str(item.get("season")),
                str(item.get("episode")),
            )
            if key not in seen:
                seen.add(key)
                title_events(item, source)
    signature = hashlib.sha256(
        json.dumps(
            [
                settings.get("trakt", {}).get("key"),
                start.isoformat(),
                [
                    (
                        r["id"],
                        [
                            (i.get("type"), i.get("tmdb"), i.get("show_tmdb"))
                            for i in r["items"]
                        ],
                    )
                    for r in followed
                ],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    with _cache_lock:
        observed = _trakt_cache.get(signature, {})
    if refresh and settings.get("trakt", {}).get("key") and followed:
        try:
            result = trakt_features.calendar(
                settings,
                followed,
                start=start,
                days=(end - start).days + 1,
                artwork_refresh=False,
            )
            warnings.extend(result.get("warnings", []))
            # Keep successful source results, retaining old rows only for a failed feed.
            failed_movie = any(
                "movie" in warning for warning in result.get("warnings", [])
            )
            failed_show = any(
                "show" in warning for warning in result.get("warnings", [])
            )
            retained = [
                item
                for item in observed.get("items", [])
                if failed_movie
                and item["type"] == "movie"
                or failed_show
                and item["type"] != "movie"
            ]
            observed = {"items": result["items"] + retained, "at": time.time()}
            with _cache_lock:
                if len(_trakt_cache) >= 24:
                    _trakt_cache.pop(next(iter(_trakt_cache)))
                _trakt_cache[signature] = observed
        except ValueError:
            warnings.append(
                "Trakt calendar could not be checked. Cached TMDB and tracked dates are still shown."
            )
    for item in observed.get("items", []):
        movie = item["type"] == "movie"
        ident = item.get("tmdb") if movie else item.get("show_tmdb")
        for entry in followed:
            if any(
                str(
                    r.get("tmdb")
                    if r["type"] in ("movie", "show")
                    else r.get("show_tmdb")
                )
                == str(ident)
                and (r["type"] == "movie") == movie
                for r in entry["items"]
            ):
                add(
                    item,
                    item.get("release_date"),
                    "expected" if movie else "episode",
                    {"type": "followed", "name": entry["name"], "list_id": entry["id"]},
                    note=(
                        "Trakt general release date; home availability is not confirmed."
                        if movie
                        else ""
                    ),
                )
    if exhausted:
        warnings.append(
            "Refresh checked up to 50 metadata records. Larger follows also use cached dates; this is not a complete release schedule."
        )
    if missing_paths and not refresh:
        warnings.append(
            "Some followed titles have no cached dates. Use Refresh dates to check providers."
        )
    # A regional theatrical/digital/disc date supersedes an ambiguous general
    # movie date on the same day; combine its provenance instead of a duplicate.
    for key, event in list(events.items()):
        if event["release_kind"] != "expected":
            continue
        targets = [
            r
            for r in events.values()
            if r["item"].get("type") == "movie"
            and r["item"].get("tmdb") == event["item"].get("tmdb")
            and r["date"] == event["date"]
            and r["release_kind"] in ("theatrical", "digital", "disc")
        ]
        if targets:
            for target in targets:
                for source in event["sources"]:
                    if source not in target["sources"]:
                        target["sources"].append(source)
            del events[key]
    return {
        "month": start.strftime("%Y-%m"),
        "items": sorted(
            events.values(),
            key=lambda r: (
                r["date"],
                r["item"].get("show_title") or r["item"]["title"],
                r["release_kind"],
            ),
        ),
        "warnings": warnings,
        "cached": not refresh,
        "checked_at": time.time() if refresh else None,
        "note": "Dates can change. Unknown dates are omitted. Episode days follow the provider's air date; a scheduled release does not confirm a playable file or regional streaming access.",
    }
