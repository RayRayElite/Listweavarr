# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only linked-list checks and durable opt-in scheduling.

Provider calls belong outside the application state lock. Results are committed
only if the original source and content fingerprint still match. Checking never
refreshes list membership or sends requests to Plex or download managers.
"""
import hashlib
import json
from urllib.parse import urlsplit

import collection_tools

HOSTS = {
    "trakt.tv",
    "app.trakt.tv",
    "letterboxd.com",
    "mdblist.com",
    "imdb.com",
    "chronocanon.com",
}
INTERVALS = {"daily": 86400, "weekly": 604800}


def supported(entry):
    try:
        return (
            urlsplit(entry.get("source") or "").hostname.removeprefix("www.") in HOSTS
        )
    except (AttributeError, ValueError):
        return False


def fingerprint(entry):
    """Ignore availability/cache updates; protect the curated order and source."""
    return hashlib.sha256(
        json.dumps(
            [
                entry.get("source"),
                entry.get("import_options"),
                [collection_tools.portable(row) for row in entry["items"]],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def summarize(before, after):
    # Occurrence indexes preserve intentional duplicates in watch orders.
    old = dict(collection_tools.indexed(before))
    new = dict(collection_tools.indexed(after))
    common_old = [key for key in old if key in new]
    common_new = [key for key in new if key in old]
    added = [row for key, row in new.items() if key not in old]
    removed = [row for key, row in old.items() if key not in new]

    def labels(rows):
        return [collection_tools.portable(row) for row in rows[:200]]

    return {
        "added": len(added),
        "removed": len(removed),
        "reordered": common_old != common_new,
        "changed": bool(added or removed or common_old != common_new),
        "added_items": labels(added),
        "removed_items": labels(removed),
        "details_truncated": len(added) > 200 or len(removed) > 200,
        "source_count": len(after),
    }


def due(state, now):
    if state.get("list_update_scheduler", {}).get("paused"):
        return None
    candidates = [
        entry
        for entry in state.get("lists", [])
        if supported(entry)
        and entry.get("update_schedule", {}).get("interval") in INTERVALS
        and entry.get("update_schedule", {}).get("next_run", 0) <= now
    ]
    return min(
        candidates,
        key=lambda e: e.get("update_schedule", {}).get("next_run", 0),
        default=None,
    )


def finish(entry, now, result=None, warning=False):
    schedule = entry.setdefault("update_schedule", {})
    if result is None:
        schedule["failures"] = min(schedule.get("failures", 0) + 1, 8)
        schedule["next_run"] = now + min(900 * 2 ** (schedule["failures"] - 1), 86400)
        schedule["last_error"] = (
            "The provider returned an incomplete or uncertain list. Review it with a manual import; no removals have been inferred."
            if warning
            else "Source check failed. Verify the connection or provider availability, then retry."
        )
    else:
        schedule.update(
            failures=0,
            last_error="",
            last_success=now,
            next_run=now + INTERVALS.get(schedule.get("interval"), 86400),
        )
        entry["update_review"] = {**result, "checked_at": now}
    schedule["last_attempt"] = now


def public(state, running=None):
    return {
        "paused": bool(state.get("list_update_scheduler", {}).get("paused")),
        "running": running,
        "lists": [
            {
                "id": e["id"],
                "name": e["name"],
                "schedule": e.get("update_schedule", {}),
                "review": e.get("update_review"),
            }
            for e in state.get("lists", [])
            if supported(e)
        ],
    }
