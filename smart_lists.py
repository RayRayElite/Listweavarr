# SPDX-License-Identifier: AGPL-3.0-only
"""Reviewed personal snapshots from saved checks, without provider or Plex writes.

First recipe: available individual movies/episodes in chosen source order.
Unknown watched history is opt-in; whole-show scopes are not guessed as unwatched.
"""
import copy
import datetime
import secrets
import threading
from collections import OrderedDict
import providers
import hashlib
import json
import time
import composite_lists
import ignored_titles
import list_sharing
import saved_lists


def preview(state, body):
    ids = body.get("sources")
    known = {row["id"]: row for row in state["lists"]}
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 20
        or any(not isinstance(value, str) or value not in known for value in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose between one and twenty distinct saved lists.")
    sources = [known[value] for value in ids]
    if sum(len(row["items"]) for row in sources) > 100000:
        raise ValueError("Choose source lists totaling at most 100,000 entries.")
    include_unknown = body.get("include_unknown") is True
    server = state.get("settings", {}).get("plex", {}).get("url")
    if not server:
        raise ValueError("Connect Plex before creating a Ready list.")
    selected, seen = [], composite_lists.Index()
    skipped = {
        "unavailable": 0,
        "scope": 0,
        "watched": 0,
        "unknown": 0,
        "ignored": 0,
        "duplicate": 0,
    }
    for source in sources:
        progress = source.get("watch_progress") or {}
        progress_known = progress.get("server") == server and progress.get(
            "checked_at", 0
        ) >= max(source.get("compared_at", 0), source.get("updated_at", 0))
        history = (
            {row["id"]: row for row in progress.get("items", [])}
            if progress_known
            else {}
        )
        for row in source["items"]:
            if row.get("type") not in ("movie", "episode"):
                skipped["scope"] += 1
                continue
            if row.get("status") != "available" or not row.get("plex_keys"):
                skipped["unavailable"] += 1
                continue
            if ignored_titles.matches(row, state.get("ignored_titles", [])):
                skipped["ignored"] += 1
                continue
            watch = history.get(row["id"], {})
            if watch.get("complete") or watch.get("state") == "watched":
                skipped["watched"] += 1
                continue
            if (
                watch.get("state") not in ("unwatched", "in_progress")
                and not include_unknown
            ):
                skipped["unknown"] += 1
                continue
            if seen.matches(row):
                skipped["duplicate"] += 1
                continue
            seen.add(row)
            selected.append(
                {
                    key: copy.deepcopy(row[key])
                    for key in (*list_sharing.FIELDS, "plex_keys", "detail", "status")
                    if key in row
                }
            )
            if len(selected) > 10000:
                raise ValueError("A Ready list supports up to 10,000 entries.")
    recipe = {"kind": "ready", "sources": ids, "include_unknown": include_unknown}
    account = state.get("settings", {}).get("plex", {})
    token = hashlib.sha256(
        json.dumps(
            {
                "recipe": recipe,
                "versions": {row["id"]: saved_lists.revision(row) for row in sources},
                "ignored": state.get("ignored_titles", []),
                "account": account,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "recipe": recipe,
        "items": selected,
        "skipped": skipped,
        "token": token,
        "note": "Based on saved Plex comparisons and watched checks, not a fresh library scan. Movies and individual episodes only; source order is preserved. No downloads or watched flags are changed.",
    }


def create(state, body, normalize):
    if body.get("confirmed") is not True:
        raise ValueError("Review the proposed smart list before creating it.")
    proposal = (
        reviewed_preview(state, body)
        if body.get("kind", "ready") != "ready"
        else preview(state, body)
    )
    if body.get("token") != proposal["token"]:
        raise ValueError(
            "The sources, watched checks or Plex connection changed. Preview again."
        )
    if not proposal["items"]:
        raise ValueError(
            "No eligible entries. Refresh source availability/watched progress or include unknown watched status."
        )
    base = {
        "ready": "Ready from my lists",
        "catchup": "Catch up before it returns",
        "comfort": "Comfort rotation",
    }[proposal["recipe"]["kind"]]
    name = base
    names = {row["name"].casefold() for row in state["lists"]}
    suffix = 2
    while name.casefold() in names:
        name = f"{base} ({suffix})"
        suffix += 1
    entry = saved_lists.edit(
        None,
        {"name": name, "description": proposal["note"], "items": proposal["items"]},
        normalize,
    )
    # Cached matches choose candidates, not permission to reuse keys from another
    # server/account. The new snapshot uses the normal explicit Plex comparison.
    entry["smart_snapshot"] = {**proposal["recipe"], "created_at": time.time()}
    state["lists"].append(entry)
    return entry


_pending = OrderedDict()
_pending_lock = threading.Lock()


def recipe(state, body):
    kind = body.get("kind")
    if kind not in ("catchup", "comfort"):
        raise ValueError("Choose a supported smart-list recipe.")
    ids = body.get("sources", [])
    known = {row["id"] for row in state["lists"]}
    if (
        not isinstance(ids, list)
        or len(ids) > 20
        or any(not isinstance(value, str) or value not in known for value in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose up to twenty distinct source lists.")
    if kind == "catchup" and not ids:
        raise ValueError("Choose lists containing shows you want to catch up on.")
    limit = body.get("limit", 50)
    if type(limit) is not int or limit not in (25, 50, 100, 500):
        raise ValueError("Choose 25, 50, 100 or 500 entries.")
    return {"kind": kind, "sources": ids, "limit": limit}


def guard(state, rule):
    by_id = {row["id"]: row for row in state["lists"]}
    return hashlib.sha256(
        json.dumps(
            {
                "rule": rule,
                "sources": {
                    identifier: (
                        saved_lists.revision(by_id[identifier])
                        if identifier in by_id
                        else None
                    )
                    for identifier in rule["sources"]
                },
                "plex": state.get("settings", {}).get("plex", {}),
                "ignored": state.get("ignored_titles", []),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def selected_shows(state, rule, today=None):
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    shows = {}
    for source in state["lists"]:
        if source["id"] not in rule["sources"]:
            continue
        for row in source["items"]:
            if row.get("type") == "movie":
                continue
            identifier = str(
                row.get("tmdb")
                if row.get("type") == "show"
                else row.get("show_tmdb") or ""
            )
            if identifier.isdigit():
                shows.setdefault(identifier, row)
    returning = []
    for identifier, row in shows.items():
        data = providers.peek_tmdb("tv/" + identifier)
        next_ep = data.get("next_episode_to_air") or {}
        last = data.get("last_episode_to_air") or {}
        try:
            release = datetime.date.fromisoformat(str(next_ep.get("air_date")))
        except ValueError:
            continue
        season = next_ep.get("season_number")
        if (
            data.get("status") not in ("Returning Series", "In Production")
            or type(season) is not int
            or season < 1
            or not 0 < (release - today).days <= 180
        ):
            continue
        if next_ep.get("episode_number") != 1 and not (
            type(last.get("season_number")) is int and season > last["season_number"]
        ):
            continue
        item = {
            "type": "show",
            "title": data.get("name") or row.get("show_title") or row["title"],
            "tmdb": identifier,
        }
        if ignored_titles.matches(item, state.get("ignored_titles", [])):
            continue
        returning.append({"item": item, "date": str(release), "season": season})
    return sorted(returning, key=lambda row: (row["date"], row["item"]["title"]))


def personal_preview(state, body, catalog, loader=None, today=None):
    rule = recipe(state, body)
    items = []
    warnings = []
    skipped = {
        key: 0
        for key in (
            "unavailable",
            "scope",
            "watched",
            "unknown",
            "ignored",
            "duplicate",
        )
    }
    if rule["kind"] == "comfort":
        scope = composite_lists.Index()
        for source in state["lists"]:
            if source["id"] not in rule["sources"]:
                continue
            for row in source["items"]:
                parent = dict(row)
                if row.get("type") in ("season", "episode"):
                    parent = {
                        "type": "show",
                        **{
                            provider: row["show_" + provider]
                            for provider in ("tmdb", "tvdb", "imdb")
                            if row.get("show_" + provider)
                        },
                    }
                scope.add(parent)
        seen = composite_lists.Index()
        for row in catalog:
            rating = float(row.get("user_rating") or 0)
            count = int(row.get("view_count") or 0)
            if (
                not row.get("watched")
                or (rating and rating < 6)
                or (rating < 8 and count < 2)
            ):
                continue
            item = {
                "type": row["type"],
                "title": row.get("title") or "Untitled",
                **{key: row[key] for key in ("year",) if row.get(key)},
                **{
                    key: str(value)
                    for key, value in row.get("ids", {}).items()
                    if key in ("tmdb", "imdb", "tvdb") and value
                },
            }
            if rule["sources"] and not scope.matches(item):
                continue
            if ignored_titles.matches(item, state.get("ignored_titles", [])):
                skipped["ignored"] += 1
                continue
            if seen.matches(item):
                skipped["duplicate"] += 1
                continue
            seen.add(item)
            data = (
                providers.peek_tmdb(
                    ("movie/" if item["type"] == "movie" else "tv/") + item["tmdb"]
                )
                if item.get("tmdb")
                else {}
            )
            item.update(
                poster=providers.image_url(data.get("poster_path")),
                reason=(f"Your rating {rating:g}/10" if rating else "")
                + (f" / {count} Plex plays" if count >= 2 else ""),
                _score=rating + min(count, 10) / 2,
                _last=row.get("last_viewed_at") or 0,
            )
            items.append(item)
        items.sort(key=lambda row: (-row["_score"], row["_last"], row["title"]))
        note = "Familiar titles from your Plex ratings and repeat plays. Low personal ratings are excluded; episode totals are never treated as show rewatches. Choose source lists to narrow the rotation, or leave them empty for your library."
    else:
        targets = selected_shows(state, rule, today)
        if len(targets) > 8:
            warnings.append(
                "First eight returning shows checked; narrow source lists to check others."
            )
        for target in targets[:8]:
            show = target["item"]
            matches = [
                row
                for row in catalog
                if row.get("type") == "show"
                and composite_lists.exact(show, {"type": "show", **row.get("ids", {})})
            ]
            if not matches:
                skipped["unavailable"] += 1
                continue
            leaves = {}
            for match in matches:
                try:
                    episodes = loader(match["key"]) if loader else []
                except (ValueError, OSError):
                    warnings.append("Could not check episodes for " + show["title"])
                    continue
                for episode in episodes:
                    coordinate = (int(episode["season"]), int(episode["episode"]))
                    if coordinate[0] < 1 or coordinate[0] >= target["season"]:
                        continue
                    previous = leaves.get(coordinate)
                    if previous is None or episode.get("watched"):
                        leaves[coordinate] = episode
            for (season, number), episode in sorted(leaves.items()):
                if episode.get("watched"):
                    skipped["watched"] += 1
                    continue
                item = {
                    "type": "episode",
                    "show_tmdb": show["tmdb"],
                    "show_title": show["title"],
                    "title": episode.get("title") or f"Episode {number}",
                    "season": str(season),
                    "episode": str(number),
                    "reason": f"{show['title']} returns {target['date']} (season {target['season']})",
                }
                if ignored_titles.matches(item, state.get("ignored_titles", [])):
                    skipped["ignored"] += 1
                    continue
                items.append(item)
        note = "Available unwatched regular episodes ahead of a known season return within 180 days. Return dates come from cached TMDB calendar metadata; episode availability/history is read from Plex. Unknown dates and already-airing seasons are excluded."
        if not targets:
            warnings.append(
                "No known season returns in these sources. Refresh their title/calendar metadata if dates are missing."
            )
    total = len(items)
    items = items[: rule["limit"]]
    if total > len(items):
        warnings.append(f"Showing {len(items)} of {total} eligible entries.")
    token = secrets.token_hex(24)
    result = {
        "recipe": rule,
        "items": items,
        "skipped": skipped,
        "token": token,
        "note": note + (" " + " ".join(warnings) if warnings else ""),
    }
    with _pending_lock:
        _pending[token] = {
            "at": time.time(),
            "guard": guard(state, rule),
            "result": copy.deepcopy(result),
        }
        while len(_pending) > 20:
            _pending.popitem(last=False)
    return result


def reviewed_preview(state, body):
    token = body.get("token")
    with _pending_lock:
        saved = copy.deepcopy(_pending.get(token)) if isinstance(token, str) else None
    if not saved or time.time() - saved["at"] > 900:
        raise ValueError("This personal preview expired. Preview again.")
    rule = recipe(state, body)
    if rule != saved["result"]["recipe"] or guard(state, rule) != saved["guard"]:
        raise ValueError("Your sources or Plex account changed. Preview again.")
    return saved["result"]
