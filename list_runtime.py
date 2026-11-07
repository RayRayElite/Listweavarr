# SPDX-License-Identifier: AGPL-3.0-only
"""Watch length from cached metadata, never a series runtime times one entry.

Rows preserve deliberate repeats and overlaps, matching the saved order. Regular
show scope excludes specials; explicit season 0 and episode entries include them.
Unknown runtimes stay unknown. An explicit fill action bounds provider requests.
"""
import math
from concurrent.futures import ThreadPoolExecutor
import providers


def minutes(value):
    return (
        float(value)
        if type(value) in (int, float) and math.isfinite(value) and 0 < value < 10000
        else None
    )


def title_path(row):
    kind = row.get("type")
    identifier = row.get("tmdb" if kind in ("movie", "show") else "show_tmdb")
    return (
        (("movie/" if kind == "movie" else "tv/") + str(identifier))
        if str(identifier or "").isdigit()
        else None
    )


def summarize(items):
    cache = {}

    def get(path):
        if path not in cache:
            cache[path] = providers.peek_tmdb(path)
        return cache[path]

    total = 0
    known_units = estimated_units = unknown_entries = estimated_entries = 0
    missing = set()
    for row in items:
        path = title_path(row)
        if not path:
            unknown_entries += 1
            continue
        parent = get(path)
        if not parent:
            missing.add(path)
        avg = next(
            (
                value
                for raw in parent.get("episode_run_time", [])
                if (value := minutes(raw))
            ),
            None,
        )
        kind = row.get("type")
        exact = estimate = unknown = 0
        if kind == "movie":
            value = minutes(parent.get("runtime"))
            if value:
                total += value
                exact = 1
            else:
                unknown = 1
        else:
            if kind in ("season", "episode"):
                seasons = [{"season_number": row.get("season")}]
            else:
                seasons = [
                    season
                    for season in parent.get("seasons", [])
                    if int(season.get("season_number") or 0) > 0
                ]
            if not seasons:
                count = parent.get("number_of_episodes")
                if type(count) is int and count > 0 and avg:
                    total += count * avg
                    estimate += count
                else:
                    unknown += 1
            for season in seasons:
                number = season.get("season_number")
                if not str(number).isdigit():
                    unknown += 1
                    continue
                season_path = path + "/season/" + str(int(number))
                data = get(season_path)
                if not data:
                    missing.add(season_path)
                episodes = data.get("episodes", [])
                if kind == "episode":
                    episodes = [
                        episode
                        for episode in episodes
                        if str(episode.get("episode_number")) == str(row.get("episode"))
                    ]
                    expected = 1
                else:
                    expected = next(
                        (
                            s.get("episode_count")
                            for s in parent.get("seasons", [])
                            if str(s.get("season_number")) == str(number)
                        ),
                        None,
                    )
                    expected = (
                        expected
                        if type(expected) is int and expected >= len(episodes)
                        else len(episodes) or None
                    )
                for episode in episodes:
                    value = minutes(episode.get("runtime"))
                    if value:
                        total += value
                        exact += 1
                    elif avg:
                        total += avg
                        estimate += 1
                    else:
                        unknown += 1
                remaining = max(0, (expected or 0) - len(episodes))
                if remaining and avg:
                    total += remaining * avg
                    estimate += remaining
                elif remaining or expected is None:
                    unknown += max(1, remaining)
        known_units += exact
        estimated_units += estimate
        estimated_entries += bool(estimate)
        unknown_entries += bool(unknown)
    return {
        "minutes": round(total, 1),
        "entries": len(items),
        "known_units": known_units,
        "estimated_units": estimated_units,
        "estimated_entries": estimated_entries,
        "unknown_entries": unknown_entries,
        "complete": unknown_entries == 0,
        "estimated": estimated_units > 0,
        "missing_paths": sorted(missing),
        "note": "Metadata runtimes; listed repeats and overlapping scopes count separately. Whole shows exclude specials. Specific file editions may differ.",
    }


def fill(items, settings):
    if not settings.get("tmdb", {}).get("key"):
        raise ValueError("Connect TMDB before filling runtime gaps.")
    errors = []
    attempted = set()
    # A second pass discovers season paths after loading a previously unknown parent.
    for _ in range(2):
        result = summarize(items)
        paths = [path for path in result["missing_paths"] if path not in attempted][
            : 20 - len(attempted)
        ]
        if not paths:
            break
        attempted.update(paths)

        def fetch(path):
            try:
                providers.cached_tmdb(path, settings)
            except (ValueError, OSError):
                return path

        with ThreadPoolExecutor(max_workers=4) as pool:
            errors.extend(path for path in pool.map(fetch, paths) if path)
    result = summarize(items)
    result.update(fetched=len(attempted), failed=len(errors))
    return result
