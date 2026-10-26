# SPDX-License-Identifier: AGPL-3.0-only
"""Regional movie release dates and TV premiere tracking.

Separates theatrical/digital/disc evidence; tracking a release is not permission to acquire media.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import datetime
import re
import time
import providers


def region(value):
    value = str(value or "CA").upper()
    if not re.fullmatch("[A-Z]{2}", value):
        raise ValueError("Choose a two-letter release country.")
    return value


def availability(identifier, country, settings, today=None):
    if not str(identifier).isdigit():
        raise ValueError("An exact movie TMDB ID is required.")
    country = region(country)
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    dates = providers.cached_tmdb(
        "movie/" + str(identifier) + "/release_dates", settings
    )
    records = next(
        (
            r.get("release_dates", [])
            for r in dates.get("results", [])
            if r.get("iso_3166_1") == country
        ),
        [],
    )
    parsed = []
    for record in records:
        try:
            date = datetime.date.fromisoformat(record["release_date"][:10])
            parsed.append((int(record["type"]), date))
        except (ValueError, KeyError, TypeError):
            continue
    home = sorted(
        (date, kind) for kind, date in parsed if kind in (4, 5) and date <= today
    )
    theatrical = sorted(
        date for kind, date in parsed if kind in (2, 3) and date <= today
    )
    upcoming = sorted(
        (date, kind) for kind, date in parsed if kind in (4, 5) and date > today
    )
    return {
        "status": "home" if home else "theatrical" if theatrical else "unknown",
        "home_date": str(home[0][0]) if home else None,
        "home_format": ("Digital" if home[0][1] == 4 else "Disc") if home else None,
        "theatrical_date": str(min((d for k, d in parsed if k in (2, 3)), default=""))
        or None,
        "digital_date": str(min((d for k, d in parsed if k == 4), default="")) or None,
        "disc_date": str(min((d for k, d in parsed if k == 5), default="")) or None,
        "expected_home_date": str(upcoming[0][0]) if upcoming else None,
        "region": country,
    }


def tv_availability(identifier, country, settings, today=None):
    if not str(identifier).isdigit():
        raise ValueError("An exact TV TMDB ID is required.")
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    data = providers.cached_tmdb("tv/" + str(identifier), settings)
    date = data.get("first_air_date") or ""
    try:
        released = datetime.date.fromisoformat(date) <= today
    except ValueError:
        date = None
        released = False
    return {
        "status": "premiered" if released else "upcoming" if date else "unknown",
        "premiere_date": date,
        "region": region(country),
        "premiere_scope": "Original series premiere; local service availability may differ.",
    }


def check(entries, settings):
    results = {}
    for entry in entries:
        try:
            info = (tv_availability if entry.get("type") == "show" else availability)(
                entry["tmdb"], entry["region"], settings
            )
            results[entry["id"]] = {**info, "checked_at": time.time(), "error": None}
            if not entry.get("poster"):
                try:
                    metadata = providers.cached_tmdb(
                        ("tv/" if entry.get("type") == "show" else "movie/")
                        + entry["tmdb"],
                        settings,
                    )
                    results[entry["id"]]["poster"] = providers.image_url(
                        metadata.get("poster_path")
                    )
                except ValueError:
                    pass
        except ValueError as exc:
            results[entry["id"]] = {"error": str(exc)}
    return results


def tracked_item(kind, identifier, country, settings):
    if (
        kind not in ("movie", "show")
        or not str(identifier).isdigit()
        or int(identifier) < 1
    ):
        raise ValueError("Choose an exact movie or TV show.")
    identifier = str(identifier)
    metadata = providers.cached_tmdb(
        ("tv/" if kind == "show" else "movie/") + identifier, settings
    )
    info = (tv_availability if kind == "show" else availability)(
        identifier, country, settings
    )
    return {
        "id": country + (":" + kind if kind == "show" else "") + ":" + identifier,
        "tmdb": identifier,
        "type": kind,
        "title": metadata.get("title") or metadata.get("name") or "Title",
        "poster": providers.image_url(metadata.get("poster_path")),
        **info,
        "region": country,
        "added_at": time.time(),
        "checked_at": time.time(),
        "acknowledged": False,
    }


def monitor(item, settings, profile, root, call):
    """Delegate future acquisition to the manager; never submit an early search."""
    service = "radarr" if item.get("type", "movie") == "movie" else "sonarr"
    request = lambda path, payload=None, method=None: call(
        settings, service, path, payload, method
    )
    if int(profile) not in [r["id"] for r in request("qualityprofile")] or root not in [
        r["path"] for r in request("rootfolder")
    ]:
        raise ValueError("Choose a valid quality profile and root folder.")
    if service == "radarr":
        found = next(
            (r for r in request("movie") if str(r.get("tmdbId")) == str(item["tmdb"])),
            None,
        )
        if found and found.get("hasFile"):
            return "Already has a file in Radarr"
        if found:
            found.update(monitored=True, minimumAvailability="released")
            request("movie/" + str(found["id"]), found, "PUT")
        else:
            found = request("movie/lookup/tmdb?tmdbId=" + str(item["tmdb"]))
            found.update(
                monitored=True,
                minimumAvailability="released",
                qualityProfileId=int(profile),
                rootFolderPath=root,
                addOptions={"searchForMovie": False},
            )
            request("movie", found, "POST")
        return "Monitored in Radarr for digital/disc release; no immediate search submitted"
    metadata = providers.cached_tmdb(
        "tv/" + str(item["tmdb"]) + "/external_ids", settings
    )
    tvdb = metadata.get("tvdb_id")
    if not tvdb:
        raise ValueError(
            "TMDB has no TVDB ID for this show; Sonarr cannot resolve it yet."
        )
    found = next(
        (r for r in request("series") if str(r.get("tvdbId")) == str(tvdb)), None
    )
    if found:
        found.update(monitored=True, monitorNewItems="all")
        for season in found.get("seasons", []):
            if season.get("seasonNumber", 0) > 0:
                season["monitored"] = True
        request("series/" + str(found["id"]), found, "PUT")
        episodes = request("episode?seriesId=" + str(found["id"]))
        ids = [
            e["id"]
            for e in episodes
            if not e.get("hasFile") and e.get("seasonNumber", 0) > 0
        ]
        if ids:
            request("episode/monitor", {"episodeIds": ids, "monitored": True}, "PUT")
    else:
        matches = request("series/lookup?term=tvdb:" + str(tvdb))
        matches = [r for r in matches if str(r.get("tvdbId")) == str(tvdb)]
        if len(matches) != 1:
            raise ValueError("Sonarr could not uniquely resolve this show.")
        found = matches[0]
        for season in found.get("seasons", []):
            season["monitored"] = season.get("seasonNumber", 0) > 0
        found.update(
            monitored=True,
            monitorNewItems="all",
            seasonFolder=True,
            qualityProfileId=int(profile),
            rootFolderPath=root,
            addOptions={
                "monitor": "all",
                "searchForMissingEpisodes": False,
                "searchForCutoffUnmetEpisodes": False,
            },
        )
        request("series", found, "POST")
    return "Monitored in Sonarr, including future seasons (excluding specials); no immediate search submitted"
