# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only download queue and manager status summaries.

Manager import is distinct from verified Plex availability. Cache status reads without turning them into new requests.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import datetime
import hashlib
import re
import threading
import time
import urllib.parse

_cache = {}
_lock = threading.RLock()


def cached(settings, service, path, call, force=False):
    cfg = settings.get(service, {})
    identity = hashlib.sha256(
        (cfg.get("url", "") + "\0" + cfg.get("key", "") + service + path).encode()
    ).hexdigest()
    with _lock:
        saved = _cache.get(identity)
        if saved and not force and time.time() - saved[0] < 60:
            return saved[1]
    value = call(settings, service, path)
    with _lock:
        _cache[identity] = (time.time(), value)
    return value


def queue(settings, service, call, force=False):
    records = []
    for page in range(1, 21):
        path = "queue?" + urllib.parse.urlencode(
            {
                "page": page,
                "pageSize": 100,
                "includeMovie": "true",
                "includeSeries": "true",
                "includeEpisode": "true",
            }
        )
        data = cached(settings, service, path, call, force)
        batch = data.get("records", []) if isinstance(data, dict) else data
        records.extend(batch)
        if not isinstance(data, dict) or len(records) >= data.get(
            "totalRecords", len(records)
        ):
            break
    return records


def queue_label(records):
    importing = any(
        str(r.get("status", "")).lower() == "completed"
        or r.get("trackedDownloadState")
        in ("importPending", "importing", "importBlocked")
        for r in records
    )
    if any(
        r.get("trackedDownloadStatus") in ("warning", "error")
        or r.get("trackedDownloadState") == "importBlocked"
        for r in records
    ):
        return "import_blocked", (
            "Import needs attention" if importing else "Download needs attention"
        )
    if importing:
        return "importing", "Waiting for import"
    return "downloading", "Downloading"


def diagnostic(result, records, service, settings):
    """Explain observed stages without inferring a successful search or import.

    Queue messages are evidence, not commands: never automatically retry, delete
    files or change permissions. Only expose bounded text, never raw responses.
    """
    state = result["state"]
    stage, summary, steps = {
        "available": ("ready", "Plex confirmed this requested scope is available.", []),
        "downloaded": (
            "plex_scan",
            "The manager reports a file; Plex availability is not confirmed yet.",
            [
                "Check the title in Plex, then refresh request status.",
                "If it is absent, check the manager's library destination and Plex's library scan.",
            ],
        ),
        "imported": (
            "plex_scan",
            "The manager reports a file; Plex availability is not confirmed yet.",
            ["Check the requested edition in Plex and refresh its library."],
        ),
        "not_managed": (
            "manager",
            "No exact matching title was found in this manager.",
            [
                "Check the request's manager route and title identity before reviewing a retry."
            ],
        ),
        "requested": (
            "waiting",
            "No active download is visible for this scope. Monitoring alone does not prove a release was found.",
            [
                "Check the manager's history and monitored episodes or movie.",
                "Review indexer availability and quality restrictions in the manager before retrying.",
            ],
        ),
        "unavailable": (
            "connection",
            "The latest status could not be verified. Previously confirmed availability is unchanged.",
            [
                "Test the saved manager route in Settings / Connections, then refresh status."
            ],
        ),
        "importing": (
            "import",
            "The download completed or is awaiting the manager's import step.",
            [
                "Check Activity / Queue in the manager for import messages.",
                "Keep the download accessible until the manager imports it.",
            ],
        ),
        "downloading": (
            "download",
            "The manager reports an active download for this scope.",
            [
                "Check the download client if progress stops. Refreshing status does not restart a download."
            ],
        ),
        "import_blocked": (
            "attention",
            "The manager reports a warning or blocked import.",
            [
                "Open Activity / Queue in the manager and review the reported reason before retrying."
            ],
        ),
    }.get(state, ("waiting", result.get("label", "Waiting for status"), []))
    evidence = []
    secrets = [
        str(cfg.get("key"))
        for cfg in settings.values()
        if isinstance(cfg, dict) and cfg.get("key")
    ]

    def clean(value):
        text = str(value or "")
        for secret in secrets:
            text = text.replace(secret, "[redacted]")
        text = re.sub(
            r"(?i)((?:api[_-]?key|token|password|authorization|x-plex-token)\s*[=:]\s*)[^\s&]+",
            r"\1[redacted]",
            text,
        )
        text = re.sub(r"https?://[^\s]+", "[link omitted]", text)
        return text[:700]

    for record in records[:30]:
        for message in (record.get("statusMessages") or [])[:10]:
            values = (
                ([message.get("title")] + list(message.get("messages") or []))
                if isinstance(message, dict)
                else [message]
            )
            for value in values:
                text = clean(value)
                if text and text not in evidence:
                    evidence.append(text)
        for field in ("errorMessage",):
            text = clean(record.get(field))
            if text and text not in evidence:
                evidence.append(text)
    evidence = evidence[:12]
    combined = " ".join(evidence).lower()
    if state == "import_blocked":
        if any(
            term in combined
            for term in ("permission", "access denied", "unauthorizedaccess")
        ):
            stage, summary = (
                "permissions",
                "The manager reports an access or permission problem.",
            )
            steps = [
                "Verify the manager's container user can read the download and write to the library destination.",
                "Check the mounted paths and ownership; do not grant unrestricted permissions as a workaround.",
            ]
        elif any(
            term in combined
            for term in (
                "eligible",
                "path does not exist",
                "directory does not exist",
                "not accessible",
                "not found",
                "no files",
            )
        ):
            stage, summary = (
                "import_path",
                "The manager cannot find an eligible file at the reported download location.",
            )
            steps = [
                "Check the completed download contains a supported, extracted media file.",
                "Verify the download client path points to the same files inside the manager container; check mounts or remote path mappings.",
            ]
        elif any(
            term in combined
            for term in ("quality", "custom format", "upgrade", "sample")
        ):
            stage, summary = (
                "import_quality",
                "The manager reports a file or quality rejection.",
            )
            steps = [
                "Review the file and rejection reason in the manager's Manual Import screen.",
                "Check the quality profile and custom-format rules before changing them.",
            ]
    return {
        "stage": stage,
        "summary": summary,
        "next_steps": steps,
        "evidence": evidence,
        "manager": service.capitalize(),
    }


def summarize(items, settings, call, force=False):
    outputs = {}
    warnings = []
    for service, kind, path in [
        ("radarr", "movie", "movie"),
        ("sonarr", "show", "series"),
    ]:
        selected = [r for r in items if (r["type"] == "movie") == (kind == "movie")]
        if not selected:
            continue
        if not settings.get(service, {}).get("key"):
            for row in selected:
                outputs[row["id"]] = {
                    "state": "unavailable",
                    "label": service.capitalize() + " not connected",
                }
            continue
        try:
            catalog = cached(settings, service, path, call, force)
            queued = queue(settings, service, call, force)
        except ValueError:
            warnings.append(
                service.capitalize()
                + " progress is unavailable; availability in Plex is unchanged."
            )
            for row in selected:
                outputs[row["id"]] = {
                    "state": "unavailable",
                    "label": "Progress unavailable",
                }
            continue
        episodes = {}
        for row in selected:
            if row.get("status") == "available":
                outputs[row["id"]] = {
                    "state": "available",
                    "label": "Available in Plex",
                    "prevent_duplicate": True,
                }
                continue

            def exact(record):
                if kind == "movie":
                    return bool(
                        row.get("tmdb")
                        and str(record.get("tmdbId")) == str(row["tmdb"])
                        or row.get("imdb")
                        and record.get("imdbId") == row["imdb"]
                    )
                identifier = (
                    row.get("show_tvdb")
                    if row["type"] in ("episode", "season")
                    else row.get("tvdb")
                )
                return bool(identifier and str(record.get("tvdbId")) == str(identifier))

            manager = next((record for record in catalog if exact(record)), None)
            if not manager:
                outputs[row["id"]] = {
                    "state": "requested" if row.get("request_log") else "not_managed",
                    "label": (
                        "Requested; awaiting manager metadata"
                        if row.get("request_log")
                        else "Not in " + service.capitalize()
                    ),
                }
                continue
            matches = [
                q
                for q in queued
                if q.get("movieId" if kind == "movie" else "seriesId") == manager["id"]
            ]
            full = False
            if kind == "movie":
                full = bool(manager.get("hasFile"))
            else:
                try:
                    if manager["id"] not in episodes:
                        episodes[manager["id"]] = cached(
                            settings,
                            service,
                            "episode?seriesId=" + str(manager["id"]),
                            call,
                            force,
                        )
                    today = (
                        datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                    )
                    scoped = [
                        e
                        for e in episodes[manager["id"]]
                        if (row["type"] != "show" or e.get("seasonNumber", 0) > 0)
                        and (
                            row["type"] == "show"
                            or str(e.get("seasonNumber")) == str(row.get("season"))
                        )
                        and (
                            row["type"] != "episode"
                            or str(e.get("episodeNumber")) == str(row.get("episode"))
                        )
                        and (e.get("airDateUtc") or "9999")[:10] <= today
                    ]
                    scoped_ids = {e["id"] for e in scoped}
                    matches = [
                        q
                        for q in matches
                        if q.get("episodeId") in scoped_ids
                        or (row["type"] == "show" and not q.get("episodeId"))
                    ]
                    full = bool(scoped) and all(e.get("hasFile") for e in scoped)
                except ValueError:
                    outputs[row["id"]] = {
                        "state": "unavailable",
                        "label": "Episode progress unavailable",
                    }
                    continue
            if full:
                outputs[row["id"]] = {
                    "state": "downloaded",
                    "label": "Imported in "
                    + service.capitalize()
                    + "; awaiting Plex comparison",
                    "prevent_duplicate": True,
                }
                continue
            if matches:
                state, label = queue_label(matches)
                total = sum(float(q.get("size") or 0) for q in matches)
                left = sum(float(q.get("sizeleft") or 0) for q in matches)
                prevent = kind == "movie" or row["type"] == "episode"
                if kind == "show" and row["type"] in ("show", "season"):
                    covered = {q.get("episodeId") for q in matches} | {
                        e["id"] for e in scoped if e.get("hasFile")
                    }
                    prevent = bool(scoped) and scoped_ids.issubset(covered)
                outputs[row["id"]] = {
                    "state": state,
                    "label": label,
                    "_queue_evidence": matches,
                    "percent": (
                        round(max(0, min(100, (1 - left / total) * 100)), 1)
                        if total
                        else None
                    ),
                    "prevent_duplicate": prevent,
                }
                continue
            outputs[row["id"]] = {
                "state": "requested",
                "label": "Monitored in "
                + service.capitalize()
                + "; no active download",
                "prevent_duplicate": False,
            }
    # Attach explanations once, preserving the exact-scope state and duplicate guards.
    for row in items:
        result = outputs.get(row["id"])
        if result is not None:
            service = "radarr" if row["type"] == "movie" else "sonarr"
            result.setdefault(
                "diagnostic",
                diagnostic(
                    result, result.pop("_queue_evidence", []), service, settings
                ),
            )
    return {"items": outputs, "warnings": warnings, "checked_at": time.time()}
