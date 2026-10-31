# SPDX-License-Identifier: AGPL-3.0-only
"""Recognize unreleased scopes from public metadata without mass network reads.

Cached dates are preferred; only current/future-year entries can trigger bounded
refreshes. Unknown dates are never invented. Callers retain ownership when a
file is already in Plex, even if its public release date is in the future.
"""
import datetime
import providers


def classify(item, settings, cache):
    kind = item.get("type")
    child = kind in ("season", "episode")
    identifier = item.get("show_tmdb") if child else item.get("tmdb")
    if not str(identifier or "").isdigit():
        return None
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    year = str(item.get("year", ""))
    can_refresh = (
        year.isdigit()
        and int(year) >= int(today[:4])
        and settings.get("tmdb", {}).get("key")
    )

    def load(path):
        key = ("release-scope", path)
        if key not in cache:
            data = providers.peek_tmdb(path)
            if not data and can_refresh and cache.get("release-fetches", 0) < 8:
                cache["release-fetches"] = cache.get("release-fetches", 0) + 1
                try:
                    data = providers.cached_tmdb(path, settings)
                except ValueError:
                    data = {}
            cache[key] = data
        return cache[key]

    path = ("movie/" if kind == "movie" else "tv/") + str(identifier)
    parent = load(path)
    data = parent
    if child:
        season = str(item.get("season", ""))
        if not season.isdigit():
            return None
        data = load(path + "/season/" + season)
        if kind == "episode":
            data = next(
                (
                    e
                    for e in data.get("episodes", [])
                    if str(e.get("episode_number")) == str(item.get("episode"))
                ),
                {},
            )
        elif not data:
            data = next(
                (
                    s
                    for s in parent.get("seasons", [])
                    if str(s.get("season_number")) == season
                ),
                {},
            )
    date = (
        data.get("release_date") or data.get("air_date") or data.get("first_air_date")
    )
    try:
        parsed = datetime.date.fromisoformat(date) if date else None
    except (TypeError, ValueError):
        parsed = None
    if parsed:
        return (
            {
                "state": "upcoming",
                "date": date,
                "detail": "Upcoming · expected " + date + "; not missing yet",
            }
            if date > today
            else {"state": "released", "date": date}
        )
    if not child and data.get("status") in (
        "Planned",
        "In Production",
        "Post Production",
        "Pilot",
    ):
        return {
            "state": "upcoming",
            "date": None,
            "detail": "Upcoming · release date not announced; not missing yet",
        }
    return None


def upcoming(item, settings, cache):
    """Compatibility helper for callers interested only in future releases."""
    result = classify(item, settings, cache)
    return result if result and result["state"] == "upcoming" else None
