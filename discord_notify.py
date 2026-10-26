# SPDX-License-Identifier: AGPL-3.0-only
"""Optional outbound request/release notifications.

Only send after the user configures and enables the destination. Never include integration credentials or download paths.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

EVENTS = {
    "available",
    "failed",
    "attention",
    "requested",
    "monitored",
    "awaiting_approval",
}


def validate_url(value):
    value = str(value or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "discord.com"
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_.-]+", parsed.path)
    ):
        raise ValueError(
            "Use a Discord HTTPS incoming webhook URL from Server Settings / Integrations."
        )
    return value


def public(state):
    cfg = state.get("discord_notifications", {})
    outbox = state.get("notification_outbox", [])
    return {
        "enabled": bool(cfg.get("enabled")),
        "configured": bool(cfg.get("url")),
        "events": cfg.get("events", ["available"]),
        "last_error": cfg.get("last_error", ""),
        "pending": sum(r.get("status") == "pending" for r in outbox),
        "failed": sum(r.get("status") == "failed" for r in outbox),
    }


def configure(state, body):
    old = state.get("discord_notifications", {})
    url = body.get("url") or old.get("url", "")
    if body.get("clear"):
        url = ""
    if url:
        validate_url(url)
    enabled = bool(body.get("enabled"))
    events = body.get("events", ["available"])
    if (
        not isinstance(events, list)
        or not events
        or any(event not in EVENTS for event in events)
    ):
        raise ValueError("Select valid notification events.")
    if enabled and not url:
        raise ValueError("Enter a Discord webhook URL before enabling notifications.")
    # Enabling/changing destination starts from now, rather than sending all old request history.
    since = (
        old.get("since", time.time())
        if old.get("enabled")
        and old.get("url") == url
        and set(old.get("events", [])) == set(events)
        else time.time()
    )
    state["discord_notifications"] = {
        "enabled": enabled,
        "url": url,
        "events": list(dict.fromkeys(events)),
        "since": since,
    }
    for job in state.get("notification_outbox", []):
        if job.get("status") == "pending" and (
            not enabled or old.get("url") != url or job.get("event") not in events
        ):
            job["status"] = "cancelled"
    return public(state)


def collect(state):
    cfg = state.get("discord_notifications", {})
    if not cfg.get("enabled") or not cfg.get("url"):
        return
    outbox = state.setdefault("notification_outbox", [])
    known = {job["id"] for job in outbox}
    destination = hashlib.sha256(cfg["url"].encode()).hexdigest()
    cursors = cfg.setdefault("collected", {})
    for request in state.get("requests", []):
        for event in request.get("events", []):
            if (
                event["at"] <= cursors.get(request["id"], 0)
                or event["at"] < cfg.get("since", 0)
                or event["status"] not in cfg.get("events", ["available"])
            ):
                continue
            identifier = hashlib.sha256(
                json.dumps([request["id"], event, destination], sort_keys=True).encode()
            ).hexdigest()
            if identifier in known:
                cursors[request["id"]] = max(cursors.get(request["id"], 0), event["at"])
                continue
            if len(outbox) >= 500:
                removable = next(
                    (job for job in outbox if job["status"] != "pending"), None
                )
                if removable:
                    outbox.remove(removable)
                else:
                    break
            known.add(identifier)
            cursors[request["id"]] = max(cursors.get(request["id"], 0), event["at"])
            scope = request["item"]["type"]
            if request["item"].get("season") is not None:
                scope += " S" + str(request["item"]["season"])
            if request["item"].get("episode") is not None:
                scope += " E" + str(request["item"]["episode"])
            content = (
                "Listweavarr - "
                + event["status"].replace("_", " ").title()
                + "\n"
                + request["item"]["title"]
                + " ("
                + scope
                + ", "
                + request.get("tier", "standard")
                + ")"
            )
            outbox.append(
                {
                    "id": identifier,
                    "status": "pending",
                    "content": content[:1900],
                    "event": event["status"],
                    "attempts": 0,
                    "next_at": 0,
                    "destination": destination,
                    "created_at": time.time(),
                }
            )
    state["notification_outbox"] = outbox[-500:]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class DeliveryError(ValueError):
    def __init__(self, message, retry_after=60, permanent=False):
        super().__init__(message)
        self.retry_after = retry_after
        self.permanent = permanent


def send(url, content):
    url = validate_url(url)
    req = urllib.request.Request(
        url + "?wait=true",
        data=json.dumps(
            {"content": str(content)[:1900], "allowed_mentions": {"parse": []}}
        ).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Listweavarr/0.4"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(
            req, timeout=10
        ) as response:
            response.read(4096)
            if response.headers.get("X-RateLimit-Remaining") == "0":
                try:
                    return max(
                        0, float(response.headers.get("X-RateLimit-Reset-After") or 0)
                    )
                except (ValueError, TypeError):
                    return 1
            return 0
    except urllib.error.HTTPError as exc:
        wait = 60
        if exc.code == 429:
            try:
                wait = max(
                    1,
                    float(
                        exc.headers.get("Retry-After")
                        or exc.headers.get("X-RateLimit-Reset-After")
                        or 60
                    ),
                )
            except ValueError:
                pass
        code = exc.code
        exc.close()
        raise DeliveryError(
            "Discord returned HTTP " + str(code) + ".",
            wait,
            code in (400, 401, 403, 404),
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DeliveryError("Discord could not be reached.", 60) from None


def next_job(state):
    cfg = state.get("discord_notifications", {})
    if (
        not cfg.get("enabled")
        or not cfg.get("url")
        or cfg.get("next_send_at", 0) > time.time()
    ):
        return None
    destination = hashlib.sha256(cfg["url"].encode()).hexdigest()
    return next(
        (
            job
            for job in state.get("notification_outbox", [])
            if job["status"] == "pending"
            and job.get("next_at", 0) <= time.time()
            and job["destination"] == destination
        ),
        None,
    )


def finish(state, identifier, error=None):
    job = next(
        (
            r
            for r in state.get("notification_outbox", [])
            if r["id"] == identifier and r["status"] == "pending"
        ),
        None,
    )
    if not job:
        return
    job["attempts"] += 1
    if error:
        job["next_at"] = time.time() + max(
            error.retry_after, min(3600, 30 * 2 ** min(job["attempts"], 6))
        )
        job["status"] = (
            "failed" if error.permanent or job["attempts"] >= 8 else "pending"
        )
        state.setdefault("discord_notifications", {})["last_error"] = str(error)
        state["discord_notifications"]["next_send_at"] = time.time() + error.retry_after
    else:
        job["status"] = "sent"
        job["sent_at"] = time.time()
        state.setdefault("discord_notifications", {}).pop("last_error", None)
