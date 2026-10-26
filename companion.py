# SPDX-License-Identifier: AGPL-3.0-only
"""Discovery workbench: Favorites, Tonight, planning and notifications.

Builds suggestions and local planning data. Session proposals do not start playback or acquire media.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import datetime
import hashlib
import re
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import explore
import providers
import taste
import ignored_titles
import manager_routes
import saved_lists


def today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def validate_state(data):
    recipes = data.get("discovery_recipes", [])
    if not isinstance(recipes, list) or len(recipes) > 50:
        raise ValueError("Invalid saved recipes.")
    for row in recipes:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("Invalid saved recipe.")
        recipe(row)
    follows = data.get("creator_follows", [])
    if (
        not isinstance(follows, list)
        or len(follows) > 30
        or any(
            not isinstance(r, dict)
            or not str(r.get("id", "")).isdigit()
            or not isinstance(r.get("name"), str)
            or r.get("role") not in ("all", "cast", "crew")
            for r in follows
        )
    ):
        raise ValueError("Invalid creator follows.")
    prefs = data.get("companion_preferences", {})
    if not isinstance(prefs, dict) or any(
        key in prefs and type(prefs[key]) is not bool
        for key in ("spoiler_safe", "log_recommendations")
    ):
        raise ValueError("Invalid discovery preferences.")
    if "notification_limit" in prefs and (
        type(prefs["notification_limit"]) is not int
        or prefs["notification_limit"] not in (5, 10, 20)
    ):
        raise ValueError("Invalid notification limit.")
    muted = prefs.get("muted_inbox", [])
    if not isinstance(muted, list) or any(
        v not in ("releases", "requests", "lists", "creators") for v in muted
    ):
        raise ValueError("Invalid inbox preferences.")
    seen = data.get("inbox_seen", [])
    if (
        not isinstance(seen, list)
        or len(seen) > 2000
        or any(not isinstance(v, str) or len(v) > 300 for v in seen)
    ):
        raise ValueError("Invalid inbox history.")
    log = data.get("discovery_impressions", {})
    if not isinstance(log, dict) or len(log) > 2000:
        raise ValueError("Invalid recommendation history.")
    for key, row in log.items():
        if (
            not isinstance(row, dict)
            or key != taste.identity(row.get("type"), row.get("tmdb"))
            or not isinstance(row.get("title"), str)
        ):
            raise ValueError("Invalid recommendation record.")
    events = data.get("creator_events", [])
    if (
        not isinstance(events, list)
        or len(events) > 1000
        or any(
            not isinstance(r, dict)
            or not isinstance(r.get("id"), str)
            or r.get("category") != "creators"
            or not isinstance(r.get("title"), str)
            or not isinstance(r.get("detail"), str)
            for r in events
        )
    ):
        raise ValueError("Invalid creator events.")
    for entry in data.get("lists", []):
        paths = entry.get("watch_paths", {})
        if not isinstance(paths, dict) or any(
            mode
            not in (
                "completionist",
                "release",
                "chronological",
                "essential",
                "recommended",
            )
            or not isinstance(ids, list)
            or len(ids) > 10000
            or any(not isinstance(i, str) for i in ids)
            or len(set(ids)) != len(ids)
            for mode, ids in paths.items()
        ):
            raise ValueError("Invalid saved watch paths.")


def recipe(body):
    kind = body.get("type", "movie")
    if kind not in ("movie", "show"):
        raise ValueError("Choose movies or TV shows.")
    name = str(body.get("name") or "My discovery recipe").strip()[:100]
    genres = body.get("genres", [])
    if (
        not isinstance(genres, list)
        or len(genres) > 4
        or any(not str(g).isdigit() for g in genres)
    ):
        raise ValueError("Choose up to four genres.")

    def number(key, default, low, high):
        try:
            value = int(body.get(key) or default)
        except (TypeError, ValueError):
            raise ValueError("Enter valid recipe numbers.") from None
        if not low <= value <= high:
            raise ValueError("Recipe " + key + " is out of range.")
        return value

    lower = number("year_from", 1900, 1870, 2200)
    upper = number("year_to", today().year, 1870, 2200)
    if lower > upper:
        raise ValueError("The first year must precede the last year.")
    dial = body.get("dial", "familiar")
    if dial not in ("familiar", "adventurous", "surprise"):
        raise ValueError("Choose a valid discovery dial.")
    availability = body.get("availability", "missing")
    if availability not in ("missing", "all"):
        raise ValueError("Choose a valid availability filter.")
    release = body.get("release", "home")
    if release not in ("home", "any"):
        raise ValueError("Choose a valid release filter.")
    return {
        "release": release,
        "name": name,
        "type": kind,
        "genres": [str(g) for g in genres],
        "tags": str(body.get("tags", "")).strip()[:200],
        "year_from": lower,
        "year_to": upper,
        "minutes": number("minutes", 180, 10, 360),
        "rating": number("rating", 6, 5, 9),
        "dial": dial,
        "availability": availability,
    }


def discover(state, body, catalog, blind=False):
    cfg = recipe(body)
    media = "movie" if cfg["type"] == "movie" else "tv"
    settings = state["settings"]
    warnings = []
    owned = explore.ownership(catalog)
    genres = providers.cached_tmdb("genre/" + media + "/list", settings).get(
        "genres", []
    )
    by_id = {str(g["id"]): g["name"] for g in genres}
    if any(g not in by_id for g in cfg["genres"]):
        raise ValueError("Choose a genre for this media type.")
    library_genres = Counter(
        g.casefold() for row in catalog for g in row.get("genres", [])
    )
    if blind:
        candidates = sorted(
            genres, key=lambda g: (library_genres[g["name"].casefold()], g["name"])
        )[:3]
        cfg["genres"] = [str(g["id"]) for g in candidates]
    params = {
        "page": max(1, min(int(body.get("page", 1)), 100)),
        "include_adult": "false",
        "sort_by": "popularity.desc",
        "vote_average.gte": cfg["rating"],
        "vote_count.gte": 150 if media == "movie" else 50,
        "with_runtime.lte": cfg["minutes"],
        ("primary_release_date.gte" if media == "movie" else "first_air_date.gte"): str(
            cfg["year_from"]
        )
        + "-01-01",
        ("primary_release_date.lte" if media == "movie" else "first_air_date.lte"): min(
            str(cfg["year_to"]) + "-12-31", str(today())
        ),
    }
    if media == "movie" and cfg["release"] == "home":
        params.update(
            {
                "region": state.get("release_region", "CA"),
                "with_release_type": "4|5",
                "release_date.lte": str(today()),
            }
        )
    if cfg["genres"]:
        params["with_genres"] = "|".join(cfg["genres"])
    keywords = []
    matched = []
    for tag in [t.strip() for t in cfg["tags"].split(",") if t.strip()][:3]:
        results = providers.cached_tmdb(
            "search/keyword?" + urllib.parse.urlencode({"query": tag}), settings
        ).get("results", [])
        exact = next(
            (r for r in results if r["name"].casefold() == tag.casefold()), None
        )
        if exact:
            keywords.append(str(exact["id"]))
            matched.append(exact["name"])
        else:
            warnings.append(
                "No exact theme tag found for " + tag + ". It was not used."
            )
    if keywords:
        params["with_keywords"] = ",".join(keywords)
    languages = state.get("explore_languages", []) or [None]
    items = []
    for language in languages:
        query = dict(params)
        if language:
            query["with_original_language"] = language
        raw_rows = []
        for offset in range(3):
            query["page"] = min(100, int(params["page"]) + offset)
            data = providers.cached_tmdb(
                "discover/" + media + "?" + urllib.parse.urlencode(query), settings
            )
            raw_rows.extend(data.get("results", []))
            if query["page"] >= int(data.get("total_pages", query["page"])):
                break
        for raw in raw_rows:
            item = explore.card(raw, media, "Recipe: " + cfg["name"])
            if (
                not explore.qualifies(item, str(cfg["rating"]) + ".0")
                or ignored_titles.matches(item, state.get("ignored_titles", []))
                or explore.tracked(item, state)
            ):
                continue
            item["in_library"] = owned(item)
            if cfg["availability"] == "missing" and item["in_library"]:
                continue
            item["reasons"] += (
                ["Genres: " + ", ".join(by_id[g] for g in cfg["genres"])]
                if cfg["genres"]
                else []
            )
            if matched:
                item["reasons"].append("Matched themes: " + ", ".join(matched))
            affinity, _ = taste.affinity(item, state.get("taste_feedback", {}))
            familiarity = sum(
                library_genres[by_id[str(g)].casefold()]
                for g in raw.get("genre_ids", [])
                if str(g) in by_id
            )
            item["_rank"] = (
                affinity + familiarity / 100
                if cfg["dial"] == "familiar"
                else (
                    -familiarity / 100
                    if cfg["dial"] == "adventurous"
                    else int(
                        hashlib.sha256(
                            (str(today()) + item["key"]).encode()
                        ).hexdigest()[:8],
                        16,
                    )
                )
            )
            items.append(item)
    unique = {r["key"]: r for r in items}
    result = sorted(unique.values(), key=lambda r: -r["_rank"])
    return {
        "items": result,
        "recipe": cfg,
        "warnings": warnings,
        "note": (
            "Library blind spots: " + ", ".join(by_id[g] for g in cfg["genres"]) + ". "
            if blind
            else ""
        )
        + "Dial reorders this result pool. Rating, language and runtime filters still apply. TV runtime is per episode; themes require exact tags.",
    }


def tonight(catalog, body, leaves, settings):
    try:
        minutes = max(10, min(int(body.get("minutes", 120)), 360))
    except (TypeError, ValueError):
        raise ValueError("Choose a valid number of minutes.") from None
    genre = str(body.get("genre", "")).casefold()
    kind = body.get("type", "both")
    if kind not in ("both", "movie", "show"):
        raise ValueError("Choose a valid media type.")
    candidates = [
        r
        for r in catalog
        if (kind == "both" or r["type"] == kind)
        and (not genre or genre in [g.casefold() for g in r.get("genres", [])])
    ]
    ranked = sorted(
        candidates,
        key=lambda r: (
            bool(r.get("watched")),
            -(r.get("user_rating") or 0),
            -(r.get("added_at") or 0),
            r.get("title", ""),
        ),
    )
    movies = []
    episodes = []
    runs = []
    for row in [r for r in ranked if r["type"] == "movie"]:
        runtime = row.get("runtime")
        if row.get("watched") and not body.get("rewatch"):
            continue
        if not isinstance(runtime, (int, float)) or not 0 < runtime <= minutes:
            continue
        movies.append(
            dict(
                row,
                type="movie",
                tmdb=(row.get("ids") or {}).get("tmdb"),
                runtime=runtime,
                reason="Available in Plex"
                + (" / Resume" if row.get("view_offset") else ""),
            )
        )
        if len(movies) >= 100:
            break
    shows = [r for r in ranked if r["type"] == "show"][:10]

    def show_choices(row):
        try:
            available = leaves(settings, row["key"])
        except (ValueError, OSError):
            return [], None
        ordered = sorted(
            [e for e in available if int(e.get("season") or 0) > 0],
            key=lambda e: (int(e["season"]), int(e["episode"])),
        )
        start = next((i for i, e in enumerate(ordered) if not e.get("watched")), None)
        if start is None:
            return [], None
        picked = []
        total = 0
        previous = None
        for episode in ordered[start:]:
            duration = episode.get("runtime") or row.get("runtime")
            coordinate = (int(episode["season"]), int(episode["episode"]))
            if previous and not (
                coordinate == (previous[0], previous[1] + 1)
                or coordinate == (previous[0] + 1, 1)
            ):
                break
            if (
                episode.get("watched")
                or not isinstance(duration, (int, float))
                or duration <= 0
                or total + duration > minutes
                or len(picked) >= 12
            ):
                break
            picked.append(
                dict(
                    episode,
                    type="episode",
                    title=row["title"]
                    + " / S"
                    + str(episode["season"])
                    + " E"
                    + str(episode["episode"]),
                    show_title=row["title"],
                    tmdb=(row.get("ids") or {}).get("tmdb"),
                    runtime=duration,
                    reason="Next unwatched episode in Plex",
                    genres=row.get("genres", []),
                )
            )
            total += duration
            previous = coordinate
        if not picked:
            return [], None
        plan = (
            {
                "key": "run:" + str(row["key"]),
                "kind": "episodes",
                "title": row["title"] + " - " + str(len(picked)) + " episodes",
                "runtime": total,
                "remaining": minutes - total,
                "reason": "Consecutive available, unwatched episodes in aired order",
                "items": picked,
            }
            if len(picked) > 1
            else None
        )
        return picked, plan

    with ThreadPoolExecutor(max_workers=4) as pool:
        for picked, plan in pool.map(show_choices, shows):
            if picked:
                episodes.append(picked[0])
            if plan:
                runs.append(plan)

    def artwork(item):
        if item.get("tmdb") and settings.get("tmdb", {}).get("key"):
            try:
                data = providers.cached_tmdb(
                    ("movie/" if item["type"] == "movie" else "tv/")
                    + str(item["tmdb"]),
                    settings,
                )
                item["poster"] = providers.image_url(data.get("poster_path"))
                if item["type"] == "movie" and data.get("belongs_to_collection"):
                    item["collection"] = data["belongs_to_collection"]
            except ValueError:
                pass
        return item

    with ThreadPoolExecutor(max_workers=4) as pool:
        items = list(pool.map(artwork, movies + episodes))
    movies = items[: len(movies)]
    episodes = items[len(movies) :]
    # Look beyond recent candidates for available sequels/prequels of seeded collections.
    collections = {
        str(r["collection"]["id"]): r["collection"]
        for r in movies
        if r.get("collection")
    }
    if collections and settings.get("tmdb", {}).get("key"):
        by_tmdb = {
            str((r.get("ids") or {}).get("tmdb")): r
            for r in candidates
            if r["type"] == "movie"
        }
        existing = {str(r.get("tmdb")) for r in movies}

        def siblings(collection):
            try:
                return (
                    providers.cached_tmdb(
                        "collection/" + str(collection["id"]), settings
                    ).get("parts", []),
                    collection,
                )
            except ValueError:
                return [], collection

        with ThreadPoolExecutor(max_workers=4) as pool:
            for parts, collection in pool.map(
                siblings, list(collections.values())[:12]
            ):
                for part in parts:
                    identifier = str(part.get("id"))
                    row = by_tmdb.get(identifier)
                    if (
                        not row
                        or identifier in existing
                        or (row.get("watched") and not body.get("rewatch"))
                    ):
                        continue
                    runtime = row.get("runtime")
                    if (
                        not isinstance(runtime, (int, float))
                        or not 0 < runtime <= minutes
                    ):
                        continue
                    movies.append(
                        dict(
                            row,
                            type="movie",
                            tmdb=identifier,
                            runtime=runtime,
                            collection=collection,
                            poster=providers.image_url(part.get("poster_path")),
                            reason="Available in Plex",
                        )
                    )
                    existing.add(identifier)
    posters = {r.get("tmdb"): r.get("poster") for r in episodes}
    for plan in runs:
        for item in plan["items"]:
            item["poster"] = posters.get(item.get("tmdb"))

    def connection(a, b):
        ca, cb = a.get("collection"), b.get("collection")
        if ca and cb and ca.get("id") == cb.get("id"):
            return 4, "Same collection: " + ca.get("name", "franchise")
        directors = set(a.get("directors", [])) & set(b.get("directors", []))
        if directors:
            return 3, "Shared director: " + ", ".join(sorted(directors))
        shared = set(a.get("genres", [])) & set(b.get("genres", []))
        if len(shared) >= 2:
            return 2, "Shared genres: " + ", ".join(sorted(shared))
        return 0, ""

    pairs = []
    for i, a in enumerate(movies):
        for b in movies[i + 1 :]:
            total = a["runtime"] + b["runtime"]
            strength, reason = connection(a, b)
            if total > minutes or not strength:
                continue
            sequence = sorted(
                [a, b], key=lambda r: (str(r.get("year") or "9999"), r["title"])
            )
            pairs.append(
                {
                    "key": "pair:" + a["key"] + ":" + b["key"],
                    "kind": "movies",
                    "title": "Movie double feature",
                    "runtime": total,
                    "remaining": minutes - total,
                    "reason": reason,
                    "items": sequence,
                    "strength": strength,
                }
            )
    pairs.sort(key=lambda p: (-p["strength"], p["remaining"], p["key"]))
    marathons = []
    for pair in pairs[:20]:
        for movie in movies:
            if (
                any(movie["key"] == r["key"] for r in pair["items"])
                or pair["runtime"] + movie["runtime"] > minutes
            ):
                continue
            links = [connection(movie, r) for r in pair["items"]]
            if not all(strength for strength, _ in links):
                continue
            picks = sorted(
                pair["items"] + [movie],
                key=lambda r: (str(r.get("year") or "9999"), r["title"]),
            )
            marathons.append(
                {
                    "key": "triple:" + ":".join(sorted(r["key"] for r in picks)),
                    "kind": "movies",
                    "title": "Three-movie marathon",
                    "runtime": sum(r["runtime"] for r in picks),
                    "remaining": minutes - sum(r["runtime"] for r in picks),
                    "reason": pair["reason"],
                    "strength": min([pair["strength"]] + [v[0] for v in links]),
                    "items": picks,
                }
            )
    mixed = []
    if kind == "both":
        for movie in movies:
            for episode in episodes:
                shared = set(movie.get("genres", [])) & set(episode.get("genres", []))
                total = movie["runtime"] + episode["runtime"]
                if shared and total <= minutes:
                    mixed.append(
                        {
                            "key": "mixed:" + movie["key"] + ":" + episode["key"],
                            "kind": "mixed",
                            "title": "Movie + an episode",
                            "runtime": total,
                            "remaining": minutes - total,
                            "reason": "Shared genre: " + ", ".join(sorted(shared)),
                            "items": [movie, episode],
                        }
                    )
    plans = []
    seen = set()
    for group in (
        runs,
        sorted(
            pairs + marathons, key=lambda p: (-p.get("strength", 0), p["remaining"])
        ),
        sorted(mixed, key=lambda p: p["remaining"]),
    ):
        count = 0
        for plan in (
            group if group is not runs else sorted(group, key=lambda p: p["remaining"])
        ):
            if plan["key"] in seen:
                continue
            seen.add(plan["key"])
            plans.append(plan)
            count += 1
            if count >= 6:
                break
    return {
        "items": movies[:24] + episodes,
        "plans": plans,
        "minutes": minutes,
        "note": "Available in Plex only. Plans never exceed your time; unknown runtimes are omitted. TV runs stop at watched episodes or gaps and use up to 12 consecutive episodes from 10 shows. Movie pairings use shared collections, directors or at least two genres. No playback starts automatically.",
    }


def franchise(state, catalog):
    settings = state["settings"]
    owned = explore.ownership(catalog)
    groups = {}
    warnings = []
    seeds = sorted(
        [r for r in catalog if r["type"] == "movie" and r.get("ids", {}).get("tmdb")],
        key=lambda r: (not r.get("watched"), -(r.get("last_viewed_at") or 0)),
    )[:30]

    def load(seed):
        try:
            title = providers.cached_tmdb("movie/" + seed["ids"]["tmdb"], settings)
            collection = title.get("belongs_to_collection")
            if not collection:
                return None
            data = providers.cached_tmdb(
                "collection/" + str(collection["id"]), settings
            )
            return seed, data
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(load, seeds):
            if not result:
                continue
            seed, data = result
            if data["id"] in groups:
                continue
            parts = []
            for raw in sorted(
                data.get("parts", []), key=lambda r: r.get("release_date") or "9999"
            ):
                item = explore.card(raw, "movie", "Member of " + data["name"])
                item["in_library"] = owned(item)
                item["upcoming"] = (raw.get("release_date") or "9999") > str(today())
                parts.append(item)
            parts = [
                r
                for r in parts
                if not ignored_titles.matches(r, state.get("ignored_titles", []))
            ]
            groups[data["id"]] = {
                "id": data["id"],
                "name": data["name"],
                "items": parts,
                "missing": sum(
                    not r["in_library"] and not r["upcoming"] for r in parts
                ),
                "watched_seed": bool(seed.get("watched")),
            }
    return {
        "groups": sorted(
            groups.values(),
            key=lambda r: (not r["watched_seed"], r["missing"] != 1, -r["missing"]),
        ),
        "note": "TMDB movie collections sampled from 30 watched/recent library movies, not a complete cross-media universe index. Release order; membership does not imply canon or essential viewing.",
    }


def priorities(state, list_id=None):
    result = []
    for entry in state["lists"]:
        if list_id and entry["id"] != list_id:
            continue
        missing = [
            (index, row)
            for index, row in enumerate(entry["items"])
            if row.get("status") in ("missing", "partial")
        ]
        for index, row in missing:
            if ignored_titles.matches(row, state.get("ignored_titles", [])):
                continue
            reasons = []
            score = 0
            if index == missing[0][0]:
                score += 40
                reasons.append("Next gap in saved watch order")
            if len(missing) == 1:
                score += 30
                reasons.append("Completes the last missing list entry")
            if row.get("status") == "partial":
                score += 20
                reasons.append("Already partly collected")
            result.append(
                {
                    "list_id": entry["id"],
                    "list_name": entry["name"],
                    "item": copy.deepcopy(row),
                    "item_id": row["id"],
                    "title": row["title"],
                    "type": row["type"],
                    "score": score,
                    "reasons": reasons or ["Missing from a saved list"],
                }
            )
    ranked = sorted(result, key=lambda r: -r["score"])[:100]

    def decorate(row):
        item = row["item"]
        identifier = (
            item.get("tmdb")
            if item["type"] in ("movie", "show")
            else item.get("show_tmdb")
        )
        data = {}
        if identifier:
            path = ("movie/" if item["type"] == "movie" else "tv/") + str(identifier)
            data = providers.peek_tmdb(path) or {}
            if not data and state.get("settings", {}).get("tmdb", {}).get("key"):
                try:
                    data = providers.cached_tmdb(path, state["settings"])
                except ValueError:
                    pass
        row["poster"] = providers.image_url(data.get("poster_path")) or item.get(
            "poster"
        )
        row["overview"] = (
            data.get("overview")
            or item.get("overview")
            or "Review this gap in its saved watch order."
        )
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(decorate, ranked))


def storage(state, body, arr_call):
    service = body.get("service", "radarr")
    route = body.get("route", "primary")
    if service not in ("radarr", "sonarr"):
        raise ValueError("Choose Radarr or Sonarr.")
    settings = manager_routes.routed(state, service, route)
    roots = arr_call(settings, service, "rootfolder")
    profiles = arr_call(settings, service, "qualityprofile")
    root = next((r for r in roots if r["path"] == body.get("root")), None)
    if not root:
        return {
            "roots": [{k: r.get(k) for k in ("path", "freeSpace")} for r in roots],
            "profiles": [{"id": p["id"], "name": p["name"]} for p in profiles],
        }
    if not any(str(p["id"]) == str(body.get("profile")) for p in profiles):
        raise ValueError("Choose a current quality profile.")
    count = int(body.get("count", 1))
    low = float(body.get("low_gb", 2))
    high = float(body.get("high_gb", 12))
    if not 1 <= count <= 10000 or not 0 < low <= high <= 1000:
        raise ValueError("Enter a valid item count and size range.")
    free = root.get("freeSpace")
    needed_low = count * low
    needed_high = count * high
    return {
        "free_gb": free / 1024**3 if isinstance(free, (int, float)) else None,
        "low_gb": needed_low,
        "high_gb": needed_high,
        "fits": (
            free >= needed_high * 1024**3 if isinstance(free, (int, float)) else None
        ),
        "note": "Planning estimate using your entered size range per movie/episode, not a prediction from the quality profile. Free space is reported by the manager for this root; mounted-drive reporting can vary. Nothing is requested.",
    }


def paths(entry, body):
    mode = body.get("mode", "completionist")
    saved = entry.get("watch_paths", {})
    if mode not in (
        "completionist",
        "release",
        "chronological",
        "essential",
        "recommended",
    ):
        raise ValueError("Choose a watch-order path.")
    if mode in saved:
        by_id = {r["id"]: r for r in entry["items"]}
        return [by_id[i] for i in saved[mode] if i in by_id], len(
            [i for i in saved[mode] if i not in by_id]
        )
    if mode == "completionist":
        return entry["items"], 0
    if mode == "release":
        return (
            sorted(
                entry["items"],
                key=lambda r: (
                    r.get("year") or "9999",
                    r.get("show_title") or r["title"],
                    int(r.get("season") or 0),
                    int(r.get("episode") or 0),
                ),
            ),
            0,
        )
    raise ValueError(
        "This path needs your curated entry selection and order. Define it first; canon and essentials are not inferred automatically."
    )


def report(state, catalog):
    impressions = state.get("discovery_impressions", {})
    watched = {
        (r["type"], str(r.get("ids", {}).get("tmdb")))
        for r in catalog
        if r.get("watched")
    }
    requests = {
        (
            ("show", str(r["item"].get("show_tmdb")))
            if r["item"]["type"] in ("episode", "season")
            else (r["item"]["type"], str(r["item"].get("tmdb")))
        )
        for r in state.get("requests", [])
        if r.get("item") and r.get("status") not in ("declined", "cancelled", "failed")
    }
    feedback = state.get("taste_feedback", {})
    counts = Counter(r["value"] for r in feedback.values())
    outcomes = []
    for row in impressions.values():
        identity = (row["type"], row["tmdb"])
        outcomes.append(
            dict(
                row,
                watched=identity in watched,
                requested=identity in requests,
                feedback=feedback.get(row["type"] + ":" + row["tmdb"], {}).get("value"),
            )
        )
    return {
        "feedback": dict(counts),
        "recommended": len(outcomes),
        "requested": sum(r["requested"] for r in outcomes),
        "watched": sum(r["watched"] for r in outcomes),
        "items": outcomes[-50:],
        "note": "Correlations since local recommendation logging was enabled, not proof recommendations caused a watch or request. Unknown/unmatched Plex IDs are not counted.",
    }


def inbox(state):
    muted = set(state.get("companion_preferences", {}).get("muted_inbox", []))
    seen = set(state.get("inbox_seen", []))
    items = []
    for row in state.get("release_watchlist", []):
        if row.get("status") in ("home", "premiered"):
            items.append(
                {
                    "id": "release:" + row["id"] + ":" + row["status"],
                    "category": "releases",
                    "title": row.get("title", "Tracked release"),
                    "detail": (
                        "Available digitally / on disc"
                        if row["status"] == "home"
                        else "TV premiere available"
                    )
                    + " - "
                    + row.get("region", "your region"),
                    "at": row.get("home_date")
                    or row.get("premiere_date")
                    or row.get("checked_at")
                    or 0,
                    "item": {
                        k: row[k]
                        for k in ("type", "tmdb", "title", "poster")
                        if k in row
                    },
                }
            )
    for row in state.get("requests", []):
        if row.get("status") in ("available", "completed", "imported"):
            items.append(
                {
                    "id": "request:" + row["id"] + ":" + row["status"],
                    "category": "requests",
                    "title": row.get("item", {}).get("title", "Request"),
                    "detail": row.get("message") or row["status"],
                    "at": row.get("updated_at") or row.get("created_at") or 0,
                    "item": copy.deepcopy(row.get("item", {})),
                    "request_id": row["id"],
                }
            )
    feed = state.get("official_feed_available", {})
    if feed.get("count", 0) > 0:
        items.append(
            {
                "id": "catalogue:" + str(feed.get("version")),
                "category": "lists",
                "title": "Official catalogue updates",
                "detail": str(feed["count"])
                + " new or updated lists available to download. Your copies and Plex playlists are unchanged.",
                "at": feed.get("checked_at", 0),
                "feed": True,
            }
        )
    import official_lists

    versions = {r["id"]: r["version"] for r in official_lists.document()["lists"]}
    for row in state["lists"]:
        version = versions.get(row.get("official_id"), 0)
        if not row.get("official_authoring") and version > row.get(
            "official_version", 0
        ):
            items.append(
                {
                    "id": "official:" + row["id"] + ":" + str(version),
                    "category": "lists",
                    "title": row["name"],
                    "detail": "Official version "
                    + str(version)
                    + " is available for review",
                    "at": row.get("updated_at") or 0,
                    "list_id": row["id"],
                }
            )
    items += state.get("creator_events", [])

    def stamp(row):
        value = row.get("at") or 0
        try:
            return float(value)
        except (ValueError, TypeError):
            try:
                return (
                    datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    .replace(tzinfo=datetime.timezone.utc)
                    .timestamp()
                )
            except (ValueError, TypeError):
                return 0

    unique = {
        row["id"]: dict(row, read=row["id"] in seen)
        for row in items
        if row["category"] not in muted
    }
    return sorted(unique.values(), key=stamp, reverse=True)[:200]


def radar(state, owned):
    events = []
    warnings = []
    now = today()
    for person in state.get("creator_follows", [])[:30]:
        try:
            data = providers.cached_tmdb(
                "person/" + person["id"] + "/combined_credits", state["settings"]
            )
        except ValueError:
            warnings.append("Could not check " + person["name"])
            continue
        rows = (data.get("cast", []) if person["role"] in ("all", "cast") else []) + (
            data.get("crew", []) if person["role"] in ("all", "crew") else []
        )
        for raw in rows:
            date = raw.get("release_date") or raw.get("first_air_date") or ""
            media = raw.get("media_type")
            if (
                media not in ("movie", "tv")
                or not str(now) <= date <= str(now + datetime.timedelta(days=365))
                or raw.get("adult")
            ):
                continue
            item = explore.card(raw, media, "Upcoming project with " + person["name"])
            if (
                owned(item)
                or ignored_titles.matches(item, state.get("ignored_titles", []))
                or explore.tracked(item, state)
            ):
                continue
            item["upcoming"] = True
            events.append(
                {
                    "id": "creator:" + person["id"] + ":" + item["key"] + ":" + date,
                    "category": "creators",
                    "title": item["title"],
                    "detail": person["name"] + " / expected " + date,
                    "at": time.time(),
                    "item": item,
                }
            )
    return list({r["id"]: r for r in events}.values()), warnings


def episode_map(settings, body):
    identifier = str(body.get("tmdb", ""))
    group = str(body.get("group", ""))
    if not identifier.isdigit() or not re.fullmatch("[A-Za-z0-9_-]{1,100}", group):
        raise ValueError("Choose a TV show and its episode group.")
    available = providers.cached_tmdb(
        "tv/" + identifier + "/episode_groups", settings
    ).get("results", [])
    if not any(r["id"] == group for r in available):
        raise ValueError("This episode group does not belong to the chosen show.")
    data = providers.cached_tmdb("tv/episode_group/" + group, settings)
    groups = sorted(data.get("groups", []), key=lambda r: r.get("order", 0))
    selected = body.get("block", "all")
    if selected != "all":
        groups = [g for g in groups if g["id"] == selected]
        if not groups:
            raise ValueError("Choose a valid episode-group block.")
    episodes = [
        e
        for g in groups
        for e in sorted(g.get("episodes", []), key=lambda e: e.get("order", 0))
    ]
    first = int(body.get("first", 1))
    last = int(body.get("last", first))
    if not 1 <= first <= last <= len(episodes) or last - first >= 1000:
        raise ValueError("Choose a valid source range, up to 1,000 episodes.")
    picked = episodes[first - 1 : last]
    if len({e["id"] for e in picked}) != len(picked):
        raise ValueError(
            "This range repeats episodes. Split it into explicitly intended blocks."
        )
    show = providers.cached_tmdb("tv/" + identifier, settings)
    seasons = {}
    items = []
    for episode in picked:
        sn = episode.get("season_number")
        en = episode.get("episode_number")
        if type(sn) is not int or type(en) is not int:
            raise ValueError("An episode lacks verified normal-season numbering.")
        if sn not in seasons:
            seasons[sn] = providers.cached_tmdb(
                "tv/" + identifier + "/season/" + str(sn), settings
            ).get("episodes", [])
        target = next(
            (
                e
                for e in seasons[sn]
                if e["episode_number"] == en and e["id"] == episode["id"]
            ),
            None,
        )
        if not target:
            raise ValueError(
                "Episode group and current aired metadata disagree. Nothing was added."
            )
        items.append(
            {
                "type": "episode",
                "show_tmdb": identifier,
                "show_title": show["name"],
                "title": target["name"],
                "season": str(sn),
                "episode": str(en),
            }
        )
    return {
        "items": items,
        "note": "Source positions "
        + str(first)
        + "–"
        + str(last)
        + " mapped through "
        + data["name"]
        + " to verified TMDB aired numbering. This maps episode order, not edited/combined media files.",
    }


def favorites(catalog, body):
    limit = max(10, min(int(body.get("limit", 50)), 100))
    values = []
    seen = set()
    for row in catalog:
        if not row.get("watched"):
            continue
        rating = float(row.get("user_rating") or 0)
        count = int(row.get("view_count") or 0)
        if rating < 8 and count < 2:
            continue
        ids = row.get("ids") or {}
        identity = (row["type"], str(ids.get("tmdb") or ids.get("imdb") or row["key"]))
        if identity in seen:
            continue
        seen.add(identity)
        item = {k: row[k] for k in ("type", "title", "year") if row.get(k) is not None}
        item.update({k: str(ids[k]) for k in ("tmdb", "tvdb", "imdb") if ids.get(k)})
        item.update(
            personal_rating=rating,
            watch_count=count,
            reasons=([f"Your Plex rating: {rating:g}/10"] if rating else [])
            + ([f"Plex play count: {count}"] if count else []),
        )
        item["_score"] = rating + min(count, 10) / 2
        metadata = (
            providers.peek_tmdb(
                ("movie/" if row["type"] == "movie" else "tv/") + str(ids.get("tmdb"))
            )
            if ids.get("tmdb")
            else {}
        )
        item["poster"] = providers.image_url(metadata.get("poster_path"))
        values.append(item)
    return {
        "items": sorted(
            values, key=lambda r: (-r["_score"], -r["personal_rating"], r["title"])
        )[:limit],
        "note": "Watched titles rated 8+/10 by you or played at least twice. Uses your connected Plex account, not audience ratings. TV play counts may be unavailable; episode totals are not treated as rewatches.",
    }
