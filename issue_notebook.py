# SPDX-License-Identifier: AGPL-3.0-only
"""Private, single-workspace playback notes with exact media scopes.

An issue is a human observation, not a file-health diagnosis or permission to
redownload/delete anything. Keep these records out of public list exports.
"""
import copy
import hashlib
import json
import math
import re
import secrets
import time
import providers
import saved_lists

CATEGORIES = {
    "playback": "Playback problem",
    "edition": "Wrong edition",
    "subtitles": "Subtitles",
    "audio": "Audio",
    "metadata": "Metadata / numbering",
    "other": "Other",
}
SEVERITIES = ("normal", "low", "high")
STATUSES = ("open", "resolved")


def canonical_item(value):
    if not isinstance(value, dict) or value.get("type") not in (
        "movie",
        "show",
        "season",
        "episode",
    ):
        raise ValueError("Choose a movie, show, season or episode for the issue.")
    title = value.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 400:
        raise ValueError("The issue needs a title up to 400 characters.")
    result = {"type": value["type"], "title": title.strip()}
    if value.get("show_title"):
        if not isinstance(value["show_title"], str) or len(value["show_title"]) > 400:
            raise ValueError("Invalid parent-show title.")
        result["show_title"] = value["show_title"]
    if value.get("year"):
        if not re.fullmatch(r"[12]\d{3}", str(value["year"])):
            raise ValueError("Use a four-digit year.")
        result["year"] = str(value["year"])
    child = value["type"] in ("season", "episode")
    for field in (
        ("season", "episode")
        if value["type"] == "episode"
        else ("season",) if child else ()
    ):
        if (
            isinstance(value.get(field), bool)
            or not str(value.get(field, "")).isdigit()
            or int(value[field]) > 100000
        ):
            raise ValueError("Choose valid season/episode numbers.")
        result[field] = str(int(value[field]))
    prefix = "show_" if child else ""
    for provider in ("tmdb", "tvdb", "imdb"):
        raw = value.get(prefix + provider)
        if raw is None or raw == "":
            continue
        raw = str(raw)
        if not re.fullmatch(
            r"tt\d{5,12}" if provider == "imdb" else r"[1-9]\d{0,11}", raw
        ):
            raise ValueError("Invalid " + provider.upper() + " identity.")
        result[prefix + provider] = raw
    return result


def revision(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


def same_scope(first, second):
    if not saved_lists.identity_keys(first).intersection(
        saved_lists.identity_keys(second)
    ):
        return False
    child = first["type"] in ("season", "episode")
    prefix = "show_" if child else ""
    return not any(
        first.get(prefix + p)
        and second.get(prefix + p)
        and str(first[prefix + p]) != str(second[prefix + p])
        for p in ("tmdb", "tvdb", "imdb")
    )


def in_scope(selected, item):
    if same_scope(selected, item):
        return True
    if selected["type"] not in ("show", "season") or item["type"] not in (
        "season",
        "episode",
    ):
        return False
    if selected["type"] == "season" and str(selected["season"]) != str(
        item.get("season")
    ):
        return False

    def parent(row):
        child = row["type"] in ("season", "episode")
        return {
            "type": "show",
            **{
                provider: row[("show_" if child else "") + provider]
                for provider in ("tmdb", "tvdb", "imdb")
                if row.get(("show_" if child else "") + provider)
            },
        }

    return same_scope(parent(selected), parent(item))


def related_requests(state, item):
    return [
        {
            "id": row["id"],
            "status": row.get("status"),
            "title": row["item"]["title"],
            "service": row.get("service"),
            "at": row.get("updated_at") or row.get("created_at"),
        }
        for row in reversed(state.get("requests", []))
        if same_scope(item, row.get("item", {}))
    ][:10]


def public(row, state):
    result = copy.deepcopy(row)
    result["revision"] = revision(row)
    result["requests"] = related_requests(state, row["item"])
    item = result["item"]
    child = item["type"] in ("season", "episode")
    identifier = item.get("show_tmdb" if child else "tmdb")
    if identifier:
        metadata = providers.peek_tmdb(
            ("movie/" if item["type"] == "movie" else "tv/") + identifier
        )
        item["poster"] = providers.image_url(metadata.get("poster_path"))
    return result


def save(state, body):
    rows = state.setdefault("library_issues", [])
    old = next((r for r in rows if r["id"] == body.get("id")), None)
    if body.get("id") and not old:
        raise ValueError("This issue no longer exists.")
    if old and body.get("revision") != revision(old):
        raise ValueError("This issue changed. Reopen it before saving.")
    if not old and len(rows) >= 5000:
        raise ValueError("The notebook supports up to 5,000 issues.")
    note = body.get("note")
    if not isinstance(note, str) or not note.strip() or len(note) > 5000:
        raise ValueError("Describe the issue in 1 to 5,000 characters.")
    category, severity, status = (
        body.get("category", "playback"),
        body.get("severity", "normal"),
        body.get("status", "open"),
    )
    if (
        not all(isinstance(value, str) for value in (category, severity, status))
        or category not in CATEGORIES
        or severity not in SEVERITIES
        or status not in STATUSES
    ):
        raise ValueError("Choose a valid issue category, priority and status.")
    row = (
        copy.deepcopy(old)
        if old
        else {"id": secrets.token_hex(12), "created_at": time.time(), "events": []}
    )
    if not old:
        entry = next(
            (r for r in state.get("lists", []) if r["id"] == body.get("list_id")), None
        )
        item = next(
            (
                r
                for r in (entry or {}).get("items", [])
                if r["id"] == body.get("item_id")
            ),
            None,
        )
        if body.get("list_id") and not item:
            raise ValueError("The selected list entry changed. Reopen its title.")
        row["item"] = canonical_item(item or body.get("item"))
        if not saved_lists.identity_keys(row["item"]) and not item:
            raise ValueError("Choose an exact provider title or a saved-list entry.")
        if item:
            row.update(list_id=entry["id"], item_id=item["id"])
    row.update(
        note=note.strip(),
        category=category,
        severity=severity,
        status=status,
        updated_at=time.time(),
    )
    action = (
        "Created"
        if not old
        else (
            "Resolved"
            if old["status"] != status and status == "resolved"
            else "Reopened" if old["status"] != status else "Updated"
        )
    )
    row["events"].append({"at": row["updated_at"], "action": action})
    row["events"] = row["events"][-30:]
    if old:
        rows[rows.index(old)] = row
    else:
        rows.append(row)
    return public(row, state)


def listing(state, body):
    query = str(body.get("query", "")).strip().casefold()
    if len(query) > 200:
        raise ValueError("Use a search up to 200 characters.")
    status, category = body.get("status", "open"), body.get("category", "all")
    if (
        not isinstance(status, str)
        or not isinstance(category, str)
        or status not in (*STATUSES, "all")
        or category not in (*CATEGORIES, "all")
    ):
        raise ValueError("Choose a valid issue filter.")
    try:
        page = int(body.get("page", 1))
    except (ValueError, TypeError):
        raise ValueError("Choose a valid notebook page.") from None
    if not 1 <= page <= 250:
        raise ValueError("Choose a valid notebook page.")
    selected = canonical_item(body["item"]) if body.get("item") else None
    rows = [
        row
        for row in state.get("library_issues", [])
        if (status == "all" or row["status"] == status)
        and (category == "all" or row["category"] == category)
        and (
            not query
            or all(
                word
                in (
                    row["item"]["title"]
                    + " "
                    + row["item"].get("show_title", "")
                    + " "
                    + row["note"]
                ).casefold()
                for word in query.split()
            )
        )
        and (
            not selected
            or in_scope(selected, row["item"])
            or not (
                saved_lists.identity_keys(selected)
                and saved_lists.identity_keys(row["item"])
            )
            and body.get("list_id")
            and body.get("list_id") == row.get("list_id")
            and body.get("item_id") == row.get("item_id")
        )
    ]
    rows.sort(
        key=lambda r: (
            r["status"] != "open",
            {"high": 0, "normal": 1, "low": 2}[r["severity"]],
            -r["updated_at"],
        )
    )
    start = (page - 1) * 20
    return {
        "items": [public(row, state) for row in rows[start : start + 20]],
        "total": len(rows),
        "has_more": start + 20 < len(rows),
        "page": page,
        "open_count": sum(
            row["status"] == "open" for row in state.get("library_issues", [])
        ),
    }


def validate_backup(rows):
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("Invalid issue notebook backup.")
    known = set()
    allowed = {
        "id",
        "item",
        "list_id",
        "item_id",
        "category",
        "severity",
        "status",
        "note",
        "created_at",
        "updated_at",
        "events",
    }
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) - allowed
            or not isinstance(row.get("id"), str)
            or not re.fullmatch(r"[a-f0-9]{24}", row["id"])
            or row["id"] in known
        ):
            raise ValueError("Invalid issue identity in backup.")
        known.add(row["id"])
        if (
            canonical_item(row.get("item")) != row["item"]
            or row.get("category") not in CATEGORIES
            or row.get("severity") not in SEVERITIES
            or row.get("status") not in STATUSES
            or not isinstance(row.get("note"), str)
            or not 0 < len(row["note"]) <= 5000
        ):
            raise ValueError("Invalid issue contents in backup.")
        for key in ("list_id", "item_id"):
            if key in row and (
                not isinstance(row[key], str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", row[key])
            ):
                raise ValueError("Invalid issue list reference.")
        for key in ("created_at", "updated_at"):
            if (
                type(row.get(key)) not in (int, float)
                or not math.isfinite(row[key])
                or not 0 <= row[key] <= 1e12
            ):
                raise ValueError("Invalid issue timestamp.")
        if not isinstance(row.get("events"), list) or len(row["events"]) > 30:
            raise ValueError("Invalid issue history.")
        for event in row["events"]:
            if (
                not isinstance(event, dict)
                or set(event) != {"at", "action"}
                or event["action"] not in ("Created", "Updated", "Resolved", "Reopened")
                or type(event["at"]) not in (int, float)
                or not math.isfinite(event["at"])
                or not 0 <= event["at"] <= 1e12
            ):
                raise ValueError("Invalid issue history.")
