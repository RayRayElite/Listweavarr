# SPDX-License-Identifier: AGPL-3.0-only
"""Validated edits to personal collections.

Protects revision consistency and requires explicit source detachment when membership/order changes.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import base64
import copy
import hashlib
import json
import re
import secrets
import time


def revision(entry):
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()


def poster(value):
    if not value:
        return ""
    if not isinstance(value, str) or len(value) > 1_500_000:
        raise ValueError("Use an image smaller than 1 MB.")
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        raise ValueError("Use a PNG, JPEG or WebP image.")
    try:
        raw = base64.b64decode(match[2], validate=True)
    except ValueError:
        raise ValueError("Invalid poster image.") from None
    valid = (
        raw.startswith(b"\x89PNG\r\n\x1a\n")
        if match[1] == "png"
        else (
            raw.startswith(b"\xff\xd8\xff")
            if match[1] == "jpeg"
            else raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
        )
    )
    if not valid or len(raw) > 1_000_000:
        raise ValueError("Invalid or oversized poster image.")
    return value


def edit(entry, body, normalize):
    if entry and body.get("revision") != revision(entry):
        raise ValueError("This list changed. Reopen the editor before saving.")
    result = (
        copy.deepcopy(entry)
        if entry
        else {"id": secrets.token_hex(8), "items": [], "source": None}
    )
    name = str(body.get("name", "")).strip()
    if not name or len(name) > 200:
        raise ValueError("Enter a list name of 1–200 characters.")
    description = str(body.get("description", "")).strip()
    if len(description) > 5000:
        raise ValueError("Keep the description under 5,000 characters.")
    result.update(
        name=name,
        description=description,
        poster=poster(body.get("poster", "")),
        playlist_poster=poster(
            body.get("playlist_poster", result.get("playlist_poster", ""))
        ),
    )
    values = body.get("items")
    if not isinstance(values, list) or len(values) > 10000:
        raise ValueError("A list supports up to 10,000 entries.")
    old = {r["id"]: r for r in result["items"]}
    rows = []
    seen = set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("Invalid list entry.")
        if value.get("id") in old:
            row = copy.deepcopy(old[value["id"]])
        else:
            row = normalize(
                {
                    k: v
                    for k, v in value.items()
                    if k
                    in (
                        "title",
                        "type",
                        "year",
                        "tmdb",
                        "tvdb",
                        "imdb",
                        "show_tmdb",
                        "show_tvdb",
                        "show_imdb",
                        "show_title",
                        "season",
                        "episode",
                        "metadata_unresolved",
                    )
                }
            )
            row["status"] = "unchecked"
        if row["id"] in seen:
            raise ValueError("Duplicate entry ID.")
        seen.add(row["id"])
        rows.append(row)
    changed = [r["id"] for r in rows] != [r["id"] for r in result["items"]]
    detach = bool(body.get("detach"))
    if result.get("source") and (changed or detach):
        if not body.get("confirm_detach"):
            raise ValueError(
                "Confirm converting this linked list to a local list before changing its entries."
            )
        result["original_source"] = result["source"]
        result["source"] = None
        result["followed"] = False
        for key in ("source_version", "source_check"):
            result.pop(key, None)
    result["items"] = rows
    result["updated_at"] = time.time()
    if (
        changed
        or result.get("playlist_poster") != (entry or {}).get("playlist_poster")
        or result.get("poster") != (entry or {}).get("poster")
    ) and result.get("playlist"):
        result["playlist_needs_update"] = True
    return result


def identity_keys(row):
    """Only exact provider IDs plus scope qualify for automatic deduplication."""
    kind = row.get("type")
    prefix = "show_" if kind in ("season", "episode") else ""
    season = str(int(row["season"])) if str(row.get("season", "")).isdigit() else ""
    episode = str(int(row["episode"])) if str(row.get("episode", "")).isdigit() else ""
    return {
        (kind, provider, str(row[prefix + provider]), season, episode)
        for provider in ("tmdb", "tvdb", "imdb")
        if row.get(prefix + provider)
    }


def update_entries(entry, items, body):
    if body.get("revision") != revision(entry):
        raise ValueError("This list changed. Reopen Add entries before saving.")
    mode = body.get("mode", "append")
    if mode not in ("append", "replace"):
        raise ValueError("Choose append or replace for the saved list.")
    result = copy.deepcopy(entry)
    old = result["items"]
    keys = set()
    skipped = 0
    reused = set()
    incoming = []
    skip = body.get("skip_duplicates", True) is not False
    if mode == "append":
        for row in old:
            keys.update(identity_keys(row))
    old_by_key = {}
    for row in old:
        for key in identity_keys(row):
            old_by_key.setdefault(key, []).append(row)
    for value in items:
        row_keys = identity_keys(value)
        if skip and row_keys.intersection(keys):
            skipped += 1
            continue
        keys.update(row_keys)
        match = None
        if mode == "replace":
            match = next(
                (
                    row
                    for key in row_keys
                    for row in old_by_key.get(key, [])
                    if row["id"] not in reused
                ),
                None,
            )
        if match:
            reused.add(match["id"])
            incoming.append(copy.deepcopy(match))
        else:
            incoming.append(dict(copy.deepcopy(value), is_new=True))
    rows = old + incoming if mode == "append" else incoming
    if len(rows) > 10000:
        raise ValueError("A saved list supports up to 10,000 entries.")
    changed = [row["id"] for row in rows] != [row["id"] for row in old]
    if changed and result.get("source"):
        if body.get("confirm_detach") is not True:
            raise ValueError(
                "Confirm converting this linked list to local before manually changing its entries. Use Refresh source to keep automatic source updates."
            )
        result["original_source"] = result["source"]
        result["source"] = None
        result["followed"] = False
        for key in ("source_version", "source_check"):
            result.pop(key, None)
    if changed:
        result["items"] = rows
        result["updated_at"] = time.time()
        if result.get("playlist"):
            result["playlist_needs_update"] = True
    old_ids = {row["id"] for row in old}
    new_ids = {row["id"] for row in rows}
    report = {
        "added": len(new_ids - old_ids),
        "removed": len(old_ids - new_ids),
        "skipped": skipped,
        "total": len(rows),
        "mode": mode,
    }
    return result, report
