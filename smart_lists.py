# SPDX-License-Identifier: AGPL-3.0-only
"""Reviewed personal snapshots from saved checks, without provider or Plex writes.

First recipe: available individual movies/episodes in chosen source order.
Unknown watched history is opt-in; whole-show scopes are not guessed as unwatched.
"""
import copy
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
        raise ValueError("Review the proposed Ready list before creating it.")
    proposal = preview(state, body)
    if body.get("token") != proposal["token"]:
        raise ValueError(
            "The sources, watched checks or Plex connection changed. Preview again."
        )
    if not proposal["items"]:
        raise ValueError(
            "No eligible entries. Refresh source availability/watched progress or include unknown watched status."
        )
    name = "Ready from my lists"
    names = {row["name"].casefold() for row in state["lists"]}
    suffix = 2
    while name.casefold() in names:
        name = f"Ready from my lists ({suffix})"
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
