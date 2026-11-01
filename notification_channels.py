# SPDX-License-Identifier: AGPL-3.0-only
"""Optional ntfy, Gotify and JSON webhook delivery with isolated durable queues.

No destination is enabled by default. Reuse the established event cursor/retry
algorithm, but keep each transport's credentials and delivery history separate.
Only titles, request scope and status leave the installation, never paths/keys.
Protocol references: https://docs.ntfy.sh/publish/ and https://gotify.net/docs/pushmsg
"""
import copy
import hashlib
import ipaddress
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import discord_notify

KINDS = ("ntfy", "gotify", "webhook")


def validate_url(value, kind):
    if kind not in KINDS:
        raise ValueError("Choose ntfy, Gotify or a JSON webhook.")
    value = str(value or "").strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Enter a valid notification endpoint URL.") from None
    if (
        len(value) > 4096
        or parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError(
            "Use a full HTTP/HTTPS endpoint without URL credentials, query parameters or fragments."
        )
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (
        address.is_link_local or address.is_multicast or address.is_unspecified
    ):
        raise ValueError("Choose a notification server address.")
    if parsed.scheme == "http" and not (
        parsed.hostname == "localhost"
        or address
        and (address.is_private or address.is_loopback)
        or "." not in parsed.hostname
        or parsed.hostname.endswith((".local", ".lan"))
    ):
        raise ValueError(
            "Use HTTPS for a public notification service; HTTP is supported for local servers."
        )
    if kind == "ntfy" and not parsed.path.strip("/"):
        raise ValueError("Include the ntfy topic in the endpoint URL.")
    if kind == "gotify" and not parsed.path.endswith("/message"):
        raise ValueError("Use your Gotify message endpoint, ending in /message.")
    return value


def signature(cfg):
    return hashlib.sha256(
        json.dumps([cfg.get("url"), cfg.get("token")]).encode()
    ).hexdigest()


def view(state, kind):
    # The Discord queue engine treats destinations as opaque strings and never
    # sends by itself. A separate outbox prevents cross-service cursor collisions.
    return {
        "discord_notifications": state.setdefault(
            "notification_channels", {}
        ).setdefault(kind, {}),
        "notification_outbox": state.setdefault("notification_outboxes", {}).setdefault(
            kind, []
        ),
        "requests": state.get("requests", []),
    }


def public(state):
    results = {}
    for kind in KINDS:
        cfg = state.get("notification_channels", {}).get(kind, {})
        outbox = state.get("notification_outboxes", {}).get(kind, [])
        results[kind] = {
            "enabled": bool(cfg.get("enabled")),
            "configured": bool(cfg.get("url")),
            "token_saved": bool(cfg.get("token")),
            "events": cfg.get("events", ["available"]),
            "batch": bool(cfg.get("batch")),
            "quiet_start": cfg.get("quiet_start", ""),
            "quiet_end": cfg.get("quiet_end", ""),
            "last_error": cfg.get("last_error", ""),
            "pending": sum(r["status"] == "pending" for r in outbox),
            "history": [
                {
                    k: row[k]
                    for k in (
                        "id",
                        "status",
                        "event",
                        "created_at",
                        "sent_at",
                        "attempts",
                        "content",
                    )
                    if k in row
                }
                for row in outbox[-20:]
            ][::-1],
        }
    return results


def configure(state, body):
    kind = body.get("kind")
    if kind not in KINDS:
        raise ValueError("Choose a notification service.")
    old = state.get("notification_channels", {}).get(kind, {})
    url = "" if body.get("clear") else body.get("url") or old.get("url", "")
    if url:
        url = validate_url(url, kind)
    token = (
        ""
        if body.get("clear") or body.get("clear_token")
        else body.get("token") or old.get("token", "")
    )
    if (
        not isinstance(token, str)
        or len(token) > 4096
        or any(ord(c) < 32 or ord(c) > 126 for c in token)
    ):
        raise ValueError("Enter a valid notification token without line breaks.")
    enabled = body.get("enabled") is True
    if enabled and (not url or kind == "gotify" and not token):
        raise ValueError(
            "Save an endpoint and, for Gotify, an application token before enabling."
        )
    events = body.get("events", ["available"])
    if (
        not isinstance(events, list)
        or not events
        or any(e not in discord_notify.EVENTS for e in events)
    ):
        raise ValueError("Select valid request events.")
    quiet = [str(body.get(key) or "") for key in ("quiet_start", "quiet_end")]
    for value in quiet:
        if value:
            if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
                raise ValueError("Quiet hours use HH:MM in the server local timezone.")
            try:
                time.strptime(value, "%H:%M")
            except ValueError:
                raise ValueError(
                    "Quiet hours use HH:MM in the Listweavarr server's local timezone."
                ) from None
    if bool(quiet[0]) != bool(quiet[1]) or quiet[0] and quiet[0] == quiet[1]:
        raise ValueError(
            "Set both quiet-hour times with different start and end times, or leave both blank."
        )
    same = (
        old.get("enabled")
        and old.get("url") == url
        and old.get("token", "") == token
        and set(old.get("events", [])) == set(events)
    )
    cfg = {
        "batch": body.get("batch") is True,
        "url": url,
        "token": token,
        "enabled": enabled,
        "events": list(dict.fromkeys(events)),
        "quiet_start": quiet[0],
        "quiet_end": quiet[1],
        "since": old.get("since", time.time()) if same else time.time(),
    }
    if same:
        for key in ("collected", "last_error", "next_send_at"):
            if key in old:
                cfg[key] = copy.deepcopy(old[key])
    state.setdefault("notification_channels", {})[kind] = cfg
    for job in state.get("notification_outboxes", {}).get(kind, []):
        if job["status"] == "pending" and (
            not enabled or not same or job.get("event") not in events
        ):
            job["status"] = "cancelled"
    return public(state)


def quiet_now(cfg, now=None):
    first, last = cfg.get("quiet_start"), cfg.get("quiet_end")
    if not first or not last:
        return False
    current = time.strftime("%H:%M", now or time.localtime())
    return (
        first <= current < last if first < last else current >= first or current < last
    )


def collect(state):
    for kind in KINDS:
        if state.get("notification_channels", {}).get(kind, {}).get("enabled"):
            data = view(state, kind)
            discord_notify.collect(data)
            state["notification_outboxes"][kind] = data["notification_outbox"]


def next_job(state):
    for kind in KINDS:
        cfg = state.get("notification_channels", {}).get(kind, {})
        if not cfg.get("enabled") or quiet_now(cfg):
            continue
        job = discord_notify.next_job(view(state, kind))
        if job:
            jobs = [copy.deepcopy(job)]
            if cfg.get("batch"):
                size = len(job["content"])
                for extra in state.get("notification_outboxes", {}).get(kind, []):
                    if (
                        extra["id"] == job["id"]
                        or extra["status"] != "pending"
                        or extra.get("next_at", 0) > time.time()
                        or extra["destination"] != job["destination"]
                    ):
                        continue
                    if len(jobs) >= 10 or size + len(extra["content"]) + 2 > 1900:
                        break
                    jobs.append(copy.deepcopy(extra))
                    size += len(extra["content"]) + 2
            outgoing = dict(
                job,
                content="\n\n".join(row["content"] for row in jobs),
                event="batch" if len(jobs) > 1 else job["event"],
            )
            return {
                "kind": kind,
                "job": outgoing,
                "jobs": jobs,
                "config": copy.deepcopy(cfg),
                "signature": signature(cfg),
            }

    return None


def finish(state, work, error=None):
    cfg = state.get("notification_channels", {}).get(work["kind"], {})
    if signature(cfg) != work["signature"]:
        return  # Do not apply a response to a replacement destination.
    for job in work.get("jobs", [work["job"]]):
        discord_notify.finish(view(state, work["kind"]), job["id"], error)


def send(kind, cfg, content, event="test"):
    url = validate_url(cfg.get("url"), kind)
    headers = {"User-Agent": "Listweavarr/0.5", "Content-Type": "application/json"}
    if kind == "ntfy":
        payload = str(content)[:1900].encode()
        headers.update(
            {"Content-Type": "text/plain; charset=utf-8", "Title": "Listweavarr"}
        )
    else:
        payload = json.dumps(
            {
                "title": "Listweavarr",
                "message": str(content)[:1900],
                **(
                    {"priority": 5}
                    if kind == "gotify"
                    else {"event": event, "source": "Listweavarr"}
                ),
            }
        ).encode()
    if cfg.get("token"):
        headers["X-Gotify-Key" if kind == "gotify" else "Authorization"] = (
            cfg["token"] if kind == "gotify" else "Bearer " + cfg["token"]
        )
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(discord_notify.NoRedirect()).open(
            request, timeout=10
        ) as response:
            response.read(4096)
    except urllib.error.HTTPError as exc:
        code = exc.code
        try:
            wait = max(1, min(86400, float(exc.headers.get("Retry-After") or 60)))
        except (ValueError, TypeError):
            wait = 60
        exc.close()
        raise discord_notify.DeliveryError(
            kind + " returned HTTP " + str(code) + ".",
            wait,
            code in (300, 301, 302, 303, 307, 308, 400, 401, 403, 404, 410, 422),
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise discord_notify.DeliveryError(
            kind + " could not be reached.", 60
        ) from None
