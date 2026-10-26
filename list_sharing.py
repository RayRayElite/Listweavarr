# SPDX-License-Identifier: AGPL-3.0-only
"""Portable list interchange without private runtime state.

Exports only public title fields, artwork and curated paths; validates every imported document before assigning local IDs.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import datetime
import csv
import io
import hashlib
import json
import secrets
import time
import saved_lists

FIELDS = (
    "type",
    "title",
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


def export_csv(entry):
    """Export ordered public identities for spreadsheet editing, without runtime state.

    Formula-looking text is escaped because spreadsheet applications can execute
    formulas even inside correctly quoted CSV cells. JSON remains the lossless
    format for covers, descriptions and alternate watch paths.
    """
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    for item in entry["items"]:
        row = {}
        for field in FIELDS:
            value = item.get(field, "")
            if isinstance(value, str) and value.lstrip().startswith(
                ("=", "+", "-", "@")
            ):
                value = "'" + value
            row[field] = value
        writer.writerow(row)
    return {"name": entry["name"], "csv": output.getvalue()}


def digest(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def export(entry, include_poster=True):
    document = {
        "format": "reelcheck-list",
        "version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "list": {
            "name": entry["name"],
            "description": entry.get("description", ""),
            "poster": (
                saved_lists.poster(entry.get("poster", "")) if include_poster else ""
            ),
            "playlist_poster": (
                saved_lists.poster(entry.get("playlist_poster", ""))
                if include_poster
                else ""
            ),
            "items": [
                {key: row[key] for key in FIELDS if key in row}
                for row in entry["items"]
            ],
        },
    }
    if entry.get("watch_paths"):
        positions = {row["id"]: index for index, row in enumerate(entry["items"])}
        document["list"]["paths"] = {
            mode: [
                positions[identifier] for identifier in ids if identifier in positions
            ]
            for mode, ids in entry["watch_paths"].items()
        }
    if len(json.dumps(document).encode()) > 7_500_000:
        raise ValueError(
            "This list is too large to share in one file. Try omitting its poster."
        )
    return document


def validate(document, normalize):
    if (
        not isinstance(document, dict)
        or document.get("format") != "reelcheck-list"
        or document.get("version") != 1
        or not isinstance(document.get("list"), dict)
    ):
        raise ValueError("Choose a Listweavarr shared-list file (version 1).")
    if len(json.dumps(document).encode()) > 7_500_000:
        raise ValueError("Shared-list files must be smaller than 7.5 MB.")
    data = document["list"]
    name = data.get("name")
    description = data.get("description", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("Shared lists need a name up to 200 characters.")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError("Keep list descriptions under 5,000 characters.")
    values = data.get("items")
    if not isinstance(values, list) or len(values) > 10000:
        raise ValueError("Shared lists support up to 10,000 entries.")
    rows = []
    counts = {kind: 0 for kind in ("movie", "show", "season", "episode")}
    unresolved = 0
    for raw in values:
        if not isinstance(raw, dict):
            raise ValueError("Invalid shared-list entry.")
        for field, value in raw.items():
            if (
                field in FIELDS
                and value is not None
                and not isinstance(value, (str, int, bool))
            ):
                raise ValueError("Shared-list fields must be text or numbers.")
        if "metadata_unresolved" in raw and not isinstance(
            raw["metadata_unresolved"], bool
        ):
            raise ValueError("Invalid unresolved-entry flag.")
        row = normalize({key: raw[key] for key in FIELDS if key in raw})
        row["status"] = "unchecked"
        row["detail"] = "Shared list - compare with your Plex server."
        rows.append(row)
        counts[row["type"]] += 1
        prefix = "show_" if row["type"] in ("season", "episode") else ""
        if row.get("metadata_unresolved") or not any(
            row.get(prefix + key) for key in ("tmdb", "tvdb", "imdb")
        ):
            unresolved += 1
    entry = {
        "id": secrets.token_hex(8),
        "name": name.strip(),
        "description": description,
        "poster": saved_lists.poster(data.get("poster", "")),
        "playlist_poster": saved_lists.poster(data.get("playlist_poster", "")),
        "items": rows,
        "source": None,
        "updated_at": time.time(),
    }
    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Invalid shared watch paths.")
    if paths:
        for mode, indices in paths.items():
            if (
                mode
                not in (
                    "essential",
                    "chronological",
                    "release",
                    "completionist",
                    "recommended",
                )
                or not isinstance(indices, list)
                or len(indices) > 10000
                or any(type(i) is not int or not 0 <= i < len(rows) for i in indices)
                or len(set(indices)) != len(indices)
            ):
                raise ValueError("Invalid shared path positions.")
        entry["watch_paths"] = {
            mode: [rows[i]["id"] for i in indices] for mode, indices in paths.items()
        }
    return entry, {
        "name": entry["name"],
        "description": description,
        "poster": entry["poster"],
        "count": len(rows),
        "types": counts,
        "needs_matching": unresolved,
        "sample": [
            {key: row[key] for key in FIELDS if key in row} for row in rows[:12]
        ],
    }
