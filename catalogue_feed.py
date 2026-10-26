# SPDX-License-Identifier: AGPL-3.0-only
"""Public catalogue download, manifest checks and staged installation.

Bounds network reads, rejects private-network targets and requires a fresh reviewed token before installation.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import hashlib
import http.client
import json
import re
import secrets
import socket
import ssl
import threading
import time
import urllib.parse
import list_sharing
import text_list_builder

MAX_BYTES = 30_000_000
PENDING = {}
GUARD = threading.Lock()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def source_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("Enter a public HTTPS catalogue link.")
    if not value.strip():
        return ""
    parsed = urllib.parse.urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError(
            "Use a public HTTPS JSON link without credentials, a custom port or a fragment."
        )
    if any(
        re.search("token|password|secret|signature|api.?key|authorization", key, re.I)
        for key, _ in urllib.parse.parse_qsl(parsed.query)
    ):
        raise ValueError("Use a public link that does not require credentials.")
    return value.strip()


def download(url):
    url = source_url(url)
    if not url:
        raise ValueError("Enter a catalogue source link first.")
    for _ in range(4):
        try:
            parsed, ip = text_list_builder.public_target(url)
            connection = http.client.HTTPSConnection(parsed.hostname, timeout=30)
            raw = socket.create_connection((ip, 443), timeout=30)
            try:
                connection.sock = ssl.create_default_context().wrap_socket(
                    raw, server_hostname=parsed.hostname
                )
            except Exception:
                raw.close()
                raise
            try:
                path = urllib.parse.urlunsplit(
                    ("", "", parsed.path or "/", parsed.query, "")
                )
                connection.request(
                    "GET",
                    path,
                    headers={
                        "User-Agent": "Listweavarr catalogue updater",
                        "Accept": "application/json,text/plain",
                        "Accept-Encoding": "identity",
                    },
                )
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    target = response.getheader("Location")
                    if not target:
                        raise ValueError("Invalid catalogue redirect.")
                    url = source_url(urllib.parse.urljoin(url, target))
                    continue
                if response.status != 200:
                    raise ValueError(
                        "Catalogue source returned HTTP "
                        + str(response.status)
                        + ". Use a public raw JSON link or import a catalogue file."
                    )
                kind = response.getheader("Content-Type", "").lower()
                if not any(
                    value in kind
                    for value in (
                        "application/json",
                        "text/plain",
                        "application/octet-stream",
                    )
                ):
                    raise ValueError(
                        "The source returned a web page instead of catalogue JSON. Use its raw/download link."
                    )
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("Catalogue files must be smaller than 30 MB.")
                try:
                    return json.loads(data.decode("utf-8-sig"))
                except (ValueError, UnicodeError):
                    raise ValueError(
                        "The source did not contain valid catalogue JSON."
                    ) from None
            finally:
                connection.close()
        except (OSError, http.client.HTTPException):
            raise ValueError(
                "Could not read the public catalogue source. Retry or import its JSON file."
            ) from None
    raise ValueError("Too many catalogue redirects.")


def validate(document, normalize):
    if (
        not isinstance(document, dict)
        or document.get("format") != "reelcheck-official-catalogue"
        or type(document.get("version")) is not int
        or document["version"] < 1
    ):
        raise ValueError("Choose a versioned Listweavarr official catalogue JSON file.")
    values = document.get("lists")
    if not isinstance(values, list) or not 1 <= len(values) <= 250:
        raise ValueError("A catalogue must contain 1–250 lists.")
    clean = []
    seen = set()
    total = 0
    for row in values:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not re.fullmatch("[A-Za-z0-9_-]{1,100}", row["id"])
            or row["id"] in seen
            or type(row.get("version")) is not int
            or row["version"] < 1
        ):
            raise ValueError(
                "Catalogue lists require unique stable IDs and positive versions."
            )
        seen.add(row["id"])
        entry, _ = list_sharing.validate(
            {"format": "reelcheck-list", "version": 1, "list": row}, normalize
        )
        if not entry["items"]:
            raise ValueError("Official lists cannot be empty.")
        total += len(entry["items"])
        if total > 100000:
            raise ValueError("A catalogue supports up to 100,000 entries.")
        portable = list_sharing.export(entry)["list"]
        portable.update(id=row["id"], version=row["version"])
        stamp = row.get("updated_at", 0)
        if not isinstance(stamp, (int, float)) or not 0 <= stamp <= 4102444800:
            stamp = 0
        portable["updated_at"] = stamp
        clean.append(portable)
    return {
        "format": "reelcheck-official-catalogue",
        "version": document["version"],
        "lists": clean,
    }


def compare_content(row):
    return {
        key: row.get(key)
        for key in (
            "name",
            "description",
            "poster",
            "playlist_poster",
            "items",
            "paths",
        )
    }


def merge(current, incoming):
    result = copy.deepcopy(current)
    by_id = {row["id"]: row for row in result["lists"]}
    added = []
    updated = []
    older = []
    for row in incoming["lists"]:
        before = by_id.get(row["id"])
        if before and before["version"] == row["version"]:
            if compare_content(before) != compare_content(row):
                raise ValueError(
                    row["name"]
                    + " changed without a new version. Ask the publisher to republish it before installing."
                )
            continue
        if before and before["version"] > row["version"]:
            older.append(row["name"])
            continue
        if before:
            result["lists"][result["lists"].index(before)] = copy.deepcopy(row)
            updated.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "from": before["version"],
                    "to": row["version"],
                    "entries": len(row["items"]),
                }
            )
        else:
            result["lists"].append(copy.deepcopy(row))
            added.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "version": row["version"],
                    "entries": len(row["items"]),
                }
            )
    if added or updated:
        result["version"] = max(current["version"] + 1, incoming["version"])
    result["format"] = "reelcheck-official-catalogue"
    return result, {
        "added": added,
        "updated": updated,
        "older": older,
        "unchanged": len(incoming["lists"]) - len(added) - len(updated) - len(older),
        "kept_local": len(
            [
                row
                for row in current["lists"]
                if row["id"] not in {r["id"] for r in incoming["lists"]}
            ]
        ),
    }


def stage(current, incoming, source=""):
    merged, summary = merge(current, incoming)
    token = secrets.token_urlsafe(24)
    with GUARD:
        for key in list(PENDING):
            if time.time() - PENDING[key]["at"] > 900:
                del PENDING[key]
        while len(PENDING) >= 2:
            del PENDING[next(iter(PENDING))]
        PENDING[token] = {
            "at": time.time(),
            "baseline": digest(current),
            "document": merged,
            "summary": summary,
            "source": source,
        }
    return {
        "token": token,
        "summary": summary,
        "source": source,
        "version": merged["version"],
    }


def reviewed(token, current):
    with GUARD:
        value = copy.deepcopy(PENDING.get(token))
    if not value or time.time() - value["at"] > 900:
        raise ValueError("This catalogue preview expired. Check the source again.")
    if digest(current) != value["baseline"]:
        raise ValueError(
            "The installed catalogue changed. Preview again before installing."
        )
    return value


def manifest(document):
    return {
        "format": "reelcheck-catalogue-manifest",
        "version": document["version"],
        "lists": [
            {
                "id": row["id"],
                "name": row["name"],
                "version": row["version"],
                "count": len(row["items"]),
            }
            for row in document["lists"]
        ],
    }


def manifest_url(url):
    parsed = urllib.parse.urlsplit(source_url(url))
    stem = parsed.path.rsplit(".", 1)[0]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, stem + ".manifest.json", parsed.query, "")
    )


def check_manifest(current, value):
    if (
        not isinstance(value, dict)
        or value.get("format") != "reelcheck-catalogue-manifest"
        or type(value.get("version")) is not int
        or value["version"] < 1
    ):
        raise ValueError(
            "This source needs an official update manifest before lightweight update checks are available."
        )
    rows = value.get("lists")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 250:
        raise ValueError("Invalid catalogue update manifest.")
    installed = {row["id"]: row["version"] for row in current["lists"]}
    changed = []
    seen = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or row["id"] in seen
            or type(row.get("version")) is not int
            or row["version"] < 1
        ):
            raise ValueError("Invalid manifest list version.")
        seen.add(row["id"])
        if row["version"] > installed.get(row["id"], 0):
            changed.append(row["id"])
    return {"configured": True, "count": len(changed), "version": value["version"]}
