# SPDX-License-Identifier: AGPL-3.0-only
"""Durable records of reviewed acquisition and monitoring requests.

A request is distinct from manager ownership and Plex availability. Public responses omit integration credentials.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import hashlib
import json
import secrets
import time
import providers

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
)


def fingerprint(item, mode="search"):
    kind = item.get("type", "movie")
    child = kind in ("season", "episode")
    prefix = "show_" if child else ""
    ids = {
        p: item.get(prefix + p)
        for p in ("tmdb", "tvdb", "imdb")
        if item.get(prefix + p)
    }
    if not ids:
        ids = {"title": item.get("title"), "year": item.get("year")}
    return hashlib.sha256(
        json.dumps(
            [
                kind,
                ids,
                item.get("season") if child else None,
                item.get("episode") if kind == "episode" else None,
                mode,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]


def routed_fingerprint(item, mode="search", route="primary"):
    key = fingerprint(item, mode)
    return (
        key
        if route == "primary"
        else hashlib.sha256((key + ":" + route).encode()).hexdigest()[:24]
    )


def record(
    state,
    item,
    mode="search",
    status="pending",
    message="Awaiting confirmation",
    options=None,
    list_id=None,
    route="primary",
    tier="standard",
):
    ledger = state.setdefault("requests", [])
    key = routed_fingerprint(item, mode, route)
    entry = next((r for r in ledger if r["id"] == key), None)
    if not entry:
        entry = {
            "id": key,
            "item": {k: copy.deepcopy(item[k]) for k in FIELDS if k in item},
            "mode": mode,
            "service": "radarr" if item["type"] == "movie" else "sonarr",
            "created_at": time.time(),
            "events": [],
            "route": route,
            "tier": tier,
        }
        ledger.append(entry)
    if status == "pending" and entry.get("status") not in (None, "pending"):
        return entry
    if status == "awaiting_approval" and entry.get("status") not in (
        None,
        "pending",
        "awaiting_approval",
        "failed",
        "declined",
        "cancelled",
    ):
        return entry
    entry.update(status=status, message=message, updated_at=time.time())
    if list_id:
        entry["list_id"] = list_id
    if options:
        entry["options"] = {"profile": str(options["profile"]), "root": options["root"]}
    entry["events"].append({"at": time.time(), "status": status, "message": message})
    entry["events"] = entry["events"][-30:]
    return entry


def migrate(state):
    for entry in state.get("lists", []):
        for item in entry["items"]:
            log = item.get("request_log")
            if (
                log
                and not log.get("ledger_id")
                and not any(
                    r["id"] == fingerprint(item) for r in state.get("requests", [])
                )
            ):
                record(
                    state,
                    item,
                    status="requested",
                    message=log.get("message", "Previously requested"),
                    list_id=entry["id"],
                )
    for row in state.get("release_watchlist", []):
        log = row.get("manager_monitor")
        if log and not any(
            r["id"] == routed_fingerprint(row, "monitor", log.get("route", "primary"))
            for r in state.get("requests", [])
        ):
            record(
                state,
                row,
                mode="monitor",
                status="monitored",
                message=log.get("message", "Release monitoring enabled"),
                route=log.get("route", "primary"),
                tier=log.get("tier", "standard"),
            )


def apply_status(state, updates):
    notices = state.setdefault("request_notifications", [])
    for request in state.get("requests", []):
        if request["id"] not in updates or request.get("status") in (
            "pending",
            "awaiting_approval",
            "declined",
            "cancelled",
        ):
            continue
        if (
            request.get("status") == "failed"
            and updates[request["id"]].get("state") != "available"
        ):
            continue
        update = updates[request["id"]]
        status = update.get("state", "unavailable")
        old = request.get("status")
        if status == "unavailable":
            request["check_warning"] = update.get("label", "Status unavailable")
            continue
        request.pop("check_warning", None)
        status = {
            "requested": (
                "monitored" if request.get("mode") == "monitor" else "requested"
            ),
            "not_managed": "requested",
            "import_blocked": "attention",
        }.get(status, status)
        request.update(
            status=status,
            message=update.get("label", status),
            percent=update.get("percent"),
            checked_at=time.time(),
        )
        if status != old:
            request.setdefault("events", []).append(
                {"at": time.time(), "status": status, "message": request["message"]}
            )
            request["events"] = request["events"][-30:]
            if status == "available" and not any(
                n.get("request_id") == request["id"] and not n.get("read")
                for n in notices
            ):
                notices.append(
                    {
                        "id": secrets.token_hex(8),
                        "request_id": request["id"],
                        "title": request["item"]["title"],
                        "at": time.time(),
                        "read": False,
                    }
                )
    state["request_notifications"] = notices[-300:]


def public(state):
    items = copy.deepcopy(state.get("requests", []))
    for row in items:
        item = row.get("item", {})
        identifier = (
            item.get("tmdb")
            if item.get("type") in ("movie", "show")
            else item.get("show_tmdb")
        )
        if identifier and not item.get("poster"):
            metadata = providers.peek_tmdb(
                ("movie/" if item.get("type") == "movie" else "tv/") + str(identifier)
            )
            poster = providers.image_url(metadata.get("poster_path"))
            if poster:
                item["poster"] = poster
    return {"items": items, "notifications": state.get("request_notifications", [])}
