# SPDX-License-Identifier: AGPL-3.0-only
"""Collection diagnostics and reviewable version merges.

Preserves personal changes and matched runtime status; keeps an undo snapshot before replacing a working copy.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import time
import hashlib
from collections import defaultdict, Counter
import list_sharing
import saved_lists


def portable(row):
    return {key: row[key] for key in list_sharing.FIELDS if key in row}


def snapshot(official):
    return {
        "name": official.get("name", ""),
        "description": official.get("description", ""),
        "poster_digest": hashlib.sha256(
            official.get("poster", "").encode()
        ).hexdigest(),
        "playlist_poster_digest": hashlib.sha256(
            official.get("playlist_poster", "").encode()
        ).hexdigest(),
        "items": copy.deepcopy(official["items"]),
        "paths": copy.deepcopy(official.get("paths", {})),
    }


def key(row):
    keys = saved_lists.identity_keys(row)
    if keys:
        return tuple(
            sorted(keys, key=lambda value: ("tmdb", "tvdb", "imdb").index(value[1]))[0]
        )
    return (
        row.get("type"),
        str(row.get("title", "")).casefold(),
        row.get("year", ""),
        str(row.get("season", "")),
        str(row.get("episode", "")),
    )


def indexed(rows):
    counts = Counter()
    result = []
    for row in rows:
        identity = key(row)
        counts[identity] += 1
        result.append(((identity, counts[identity]), row))
    return result


def health(entry):
    issues = []
    seen = {}
    episodes = defaultdict(list)
    whole = defaultdict(list)
    for position, row in enumerate(entry["items"], 1):
        title = row.get("show_title") or row.get("title", "Untitled")
        kind = row.get("type")
        identity = key(row)

        def note(code, message):
            issues.append(
                {
                    "code": code,
                    "title": title,
                    "positions": [position],
                    "message": message,
                }
            )

        if identity in seen:
            issues.append(
                {
                    "code": "duplicate",
                    "title": title,
                    "positions": [seen[identity], position],
                    "message": "Exact title and TV scope appears more than once. Repeats can be intentional.",
                }
            )
        else:
            seen[identity] = position
        prefix = "show_" if kind in ("season", "episode") else ""
        provider = next(
            (
                (p, str(row[prefix + p]))
                for p in ("tmdb", "tvdb", "imdb")
                if row.get(prefix + p)
            ),
            None,
        )
        if not provider or row.get("metadata_unresolved"):
            note(
                "unmatched",
                "No verified parent/title identity. Review the match before requesting it.",
            )
        if kind in ("season", "episode") and not str(row.get("season", "")).isdigit():
            note("scope", "Missing or invalid season number.")
            continue
        if kind == "episode" and (
            not str(row.get("episode", "")).isdigit() or int(row["episode"]) < 1
        ):
            note("scope", "Missing or invalid episode number.")
            continue
        if provider:
            group = (provider, str(row.get("season", "")))
            if kind == "episode":
                episodes[group].append((int(row["episode"]), position, title))
            if kind == "season":
                whole[group].append(position)
            if kind == "show":
                whole[(provider, "*")].append(position)
    for (provider, season), values in episodes.items():
        coverage = whole.get((provider, season), []) + whole.get((provider, "*"), [])
        if coverage:
            issues.append(
                {
                    "code": "overlap",
                    "title": values[0][2],
                    "positions": coverage + [v[1] for v in values[:8]],
                    "message": "Whole show/season and individual episodes overlap. This may be intentional in a watch order.",
                }
            )
        unique = sorted({v[0] for v in values})
        gaps = [
            f"{a+1}-{b-1}" if b - a > 2 else str(a + 1)
            for a, b in zip(unique, unique[1:])
            if b - a > 1
        ]
        if gaps:
            issues.append(
                {
                    "code": "gap",
                    "title": values[0][2],
                    "positions": [],
                    "message": "Season "
                    + season
                    + " has gaps between listed episodes: "
                    + ", ".join(gaps[:10])
                    + ". Curated lists may intentionally omit episodes.",
                }
            )
    return {
        "name": entry["name"],
        "entries": len(entry["items"]),
        "total": len(issues),
        "issues": issues[:300],
        "truncated": len(issues) > 300,
        "counts": dict(Counter(row["code"] for row in issues)),
        "note": "Structural checks only. Provider availability and download status are not checked. No entries were changed.",
    }


def preview(entry, official):
    current = dict(indexed(entry["items"]))
    incoming = dict(indexed(official["items"]))
    common = set(current) & set(incoming)
    added = [
        row.get("title", "Untitled")
        for token, row in incoming.items()
        if token not in current
    ]
    removed = [
        row.get("title", "Untitled")
        for token, row in current.items()
        if token not in incoming
    ]
    return {
        "name": entry["name"],
        "list_id": entry["id"],
        "revision": saved_lists.revision(entry),
        "installed_version": entry.get("official_version", 0),
        "version": official["version"],
        "available": official["version"] > entry.get("official_version", 0),
        "added": added,
        "removed": removed,
        "order_changed": [t for t in current if t in common]
        != [t for t in incoming if t in common],
        "changed": sum(portable(current[t]) != portable(incoming[t]) for t in common),
        "has_baseline": bool(entry.get("official_base")),
        "can_rollback": bool(entry.get("official_undo")),
    }


def apply_update(entry, official, mode, normalize):
    if mode not in ("merge", "replace"):
        raise ValueError("Choose preserve personal changes or official order.")
    if entry.get("official_authoring"):
        raise ValueError(
            "This is an official authoring original. Publish changes instead of updating it as a personal copy."
        )
    if official["version"] <= entry.get("official_version", 0):
        raise ValueError("This copy already has the current official version.")
    result = copy.deepcopy(entry)
    current = dict(indexed(entry["items"]))
    incoming = dict(indexed(official["items"]))
    baseline = entry.get("official_base")
    base = dict(indexed(baseline.get("items", []))) if baseline else {}
    rows = []
    for token, row in incoming.items():
        if mode == "merge" and baseline and token in base and token not in current:
            continue
        existing = current.get(token)
        if existing:
            value = copy.deepcopy(existing)
            if (
                mode == "replace"
                or baseline
                and token in base
                and portable(existing) == portable(base[token])
            ):
                for field in list_sharing.FIELDS:
                    value.pop(field, None)
                value.update(portable(row))
        else:
            value = dict(normalize(portable(row)), status="unchecked")
        rows.append(value)
    if mode == "merge":
        rows.extend(
            copy.deepcopy(row)
            for token, row in current.items()
            if token not in incoming
            and (
                not baseline
                or token not in base
                or portable(row) != portable(base[token])
            )
        )
    if len(rows) > 10000:
        raise ValueError("Merged collection exceeds 10,000 entries.")
    for field in ("name", "description", "poster", "playlist_poster"):
        unchanged = bool(baseline) and (
            hashlib.sha256(entry.get(field, "").encode()).hexdigest()
            == baseline[field + "_digest"]
            if field in ("poster", "playlist_poster") and field + "_digest" in baseline
            else entry.get(field, "") == baseline.get(field, "")
        )
        if mode == "replace" or unchanged:
            result[field] = official.get(field, "")
    undo = copy.deepcopy(entry)
    undo.pop("official_undo", None)
    source_tokens = [token for token, _ in indexed(official["items"])]
    targets = {token: value["id"] for token, value in indexed(rows)}
    incoming_paths = {
        name: [
            targets[source_tokens[i]]
            for i in indices
            if 0 <= i < len(source_tokens) and source_tokens[i] in targets
        ]
        for name, indices in official.get("paths", {}).items()
    }
    if mode == "replace":
        if incoming_paths:
            result["watch_paths"] = incoming_paths
        else:
            result.pop("watch_paths", None)
    elif incoming_paths:
        paths = result.setdefault("watch_paths", {})
        current_tokens = {
            value["id"]: token for token, value in indexed(entry["items"])
        }
        base_tokens = [token for token, _ in indexed((baseline or {}).get("items", []))]
        for name, ids in incoming_paths.items():
            base_indices = (baseline or {}).get("paths", {}).get(name)
            base_order = (
                [base_tokens[i] for i in base_indices if 0 <= i < len(base_tokens)]
                if base_indices is not None
                else None
            )
            local_order = [current_tokens.get(i) for i in paths.get(name, [])]
            if (
                name not in paths
                or base_order is not None
                and local_order == base_order
            ):
                paths[name] = ids
    result.update(
        items=rows,
        official_version=official["version"],
        official_base=snapshot(official),
        official_undo=undo,
        updated_at=time.time(),
    )
    if result.get("playlist"):
        result["playlist_needs_update"] = True
    return result


def rollback(entry):
    if not entry.get("official_undo"):
        raise ValueError("No previous official update is available to undo.")
    result = copy.deepcopy(entry["official_undo"])
    result["updated_at"] = time.time()
    current = {row["id"]: row for row in entry["items"]}
    for row in result["items"]:
        if row["id"] in current:
            row.update(
                {
                    key: copy.deepcopy(value)
                    for key, value in current[row["id"]].items()
                    if key not in list_sharing.FIELDS
                }
            )
    if entry.get("playlist"):
        result["playlist"] = copy.deepcopy(entry["playlist"])
        result["playlist_needs_update"] = True
    return result
