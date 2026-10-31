# SPDX-License-Identifier: AGPL-3.0-only
"""Linked-list checks, pinned source updates and durable opt-in scheduling.

Provider calls belong outside the application state lock. Results are committed
only if the original source and content fingerprint still match. Checking never
refreshes list membership or sends requests to Plex or download managers.
Explicit apply/undo operations affect only the local saved list.
"""
import hashlib
import json
import copy
import secrets
from urllib.parse import urlsplit

import collection_tools
import list_sharing

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
                entry.get("watch_paths"),
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
    entry.pop("update_pending", None)
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


def stage(entry, rows, source_version, now):
    """Pin reviewed public content; applying must never refetch the provider."""
    entry["update_pending"] = {
        "token": secrets.token_hex(16),
        "base": fingerprint(entry),
        "items": [collection_tools.portable(row) for row in rows],
        "source_version": source_version,
        "checked_at": now,
    }


def preview(entry, token):
    pending = entry.get("update_pending")
    if (
        not pending
        or pending["token"] != token
        or pending["base"] != fingerprint(entry)
    ):
        raise ValueError("This source preview is stale. Check the list again.")
    positions = {
        identity: index
        for index, (identity, _) in enumerate(
            collection_tools.indexed(entry["items"]), 1
        )
    }
    return {
        "token": token,
        "items": [
            {**row, "previous_position": positions.get(identity)}
            for identity, row in collection_tools.indexed(pending["items"])
        ],
    }


def apply(entry, token, now, normalize):
    pending = entry.get("update_pending")
    if (
        not pending
        or token != pending["token"]
        or pending["base"] != fingerprint(entry)
    ):
        raise ValueError(
            "This source preview is stale. Check the list again before applying."
        )
    before = copy.deepcopy(entry)
    previous = dict(collection_tools.indexed(entry["items"]))
    rows = []
    for identity, value in collection_tools.indexed(pending["items"]):
        old = previous.get(identity)
        rows.append({**old, **value} if old else normalize(value))
    entry["items"] = rows
    valid = {row["id"] for row in rows}
    if "watch_paths" in entry:
        entry["watch_paths"] = {
            name: [ident for ident in ids if ident in valid]
            for name, ids in entry["watch_paths"].items()
        }
    if pending.get("source_version"):
        entry["source_version"] = pending["source_version"]
    entry["updated_at"] = now
    if entry.get("playlist") and fingerprint(entry) != fingerprint(before):
        entry["playlist_needs_update"] = True
    entry.pop("update_pending", None)
    entry["update_review"] = {
        "changed": False,
        "added": 0,
        "removed": 0,
        "reordered": False,
        "checked_at": now,
        "applied_at": now,
    }
    entry.pop("source_check", None)
    entry["source_update_undo"] = {
        "items": before["items"],
        "watch_paths": before.get("watch_paths"),
        "source_version": before.get("source_version"),
        "after": fingerprint(entry),
        "token": secrets.token_hex(16),
    }


def undo(entry, token, now):
    previous = entry.get("source_update_undo")
    if (
        not previous
        or token != previous["token"]
        or previous["after"] != fingerprint(entry)
    ):
        raise ValueError(
            "This list changed since the source update. Undo cannot overwrite later edits."
        )
    current = {row["id"]: row for row in entry["items"]}
    # Keep fresh availability/watch flags while restoring the original curation.
    entry["items"] = [
        {
            **row,
            **{
                key: value
                for key, value in current.get(row["id"], {}).items()
                if key not in list_sharing.FIELDS and key != "id"
            },
        }
        for row in previous["items"]
    ]
    for field in ("watch_paths", "source_version"):
        if previous[field] is None:
            entry.pop(field, None)
        else:
            entry[field] = previous[field]
    entry["updated_at"] = now
    if entry.get("playlist"):
        entry["playlist_needs_update"] = True
    for field in (
        "source_update_undo",
        "update_pending",
        "update_review",
        "source_check",
    ):
        entry.pop(field, None)


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
                "apply_token": (
                    e["update_pending"]["token"]
                    if e.get("update_pending")
                    and e["update_pending"]["base"] == fingerprint(e)
                    else None
                ),
                "undo_token": (
                    e["source_update_undo"]["token"]
                    if e.get("source_update_undo")
                    and e["source_update_undo"]["after"] == fingerprint(e)
                    else None
                ),
            }
            for e in state.get("lists", [])
            if supported(e)
        ],
    }
