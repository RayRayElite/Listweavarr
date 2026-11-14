# SPDX-License-Identifier: AGPL-3.0-only
"""Small, capability-scoped bookmark store; never changes Plex watch history."""
import hmac
import json
import time
import base64
import hashlib
from pathlib import Path


def authorize(state, authorization):
    token = state.get("playlist_progress_token", "")
    return bool(token) and hmac.compare_digest(
        ("Bearer " + token).encode(), str(authorization).encode()
    )


def merge(state, body):
    rows = body.get("items", [])
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("Too many bookmarks")
    machine = state.get("playlist_artwork_pairing", {}).get("machine")
    scopes = body.get("scopes", [])
    if not isinstance(scopes, list) or len(scopes) > 1000:
        raise ValueError("Invalid scopes")
    allowed = set()
    for scope in scopes:
        if not isinstance(scope, dict) or scope.get("serverId") != machine:
            raise ValueError("Wrong server")
        values = [scope.get(k) for k in ("serverId", "userId", "playlistId")]
        if any(not isinstance(v, str) or not v or len(v) > 300 for v in values):
            raise ValueError("Invalid scope")
        allowed.add(tuple(values))
    # Validate the complete request before changing any state.
    incoming = []
    now = int(time.time() * 1000)
    for row in rows:
        if not isinstance(row, dict) or len(json.dumps(row)) > 12000:
            raise ValueError("Invalid bookmark")
        key = tuple(row.get(k) for k in ("serverId", "userId", "playlistId"))
        if key not in allowed or row.get("schema") != 1:
            raise ValueError("Bookmark outside scope")
        for field in ("entryId", "ratingKey", "sessionId"):
            if not isinstance(row.get(field), str) or not 0 < len(row[field]) <= 300:
                raise ValueError("Invalid entry")
        for field in ("offsetMs", "revision", "updatedAt", "ratingKeyOccurrences"):
            value = row.get(field)
            if type(value) is not int or not 0 <= value <= 9007199254740991:
                raise ValueError("Invalid bookmark number")
        if (
            row["updatedAt"] > now + 300000
            or row["ratingKeyOccurrences"] < 1
            or ("dismissed" in row and type(row["dismissed"]) is not bool)
            or type(row.get("completed")) is not bool
        ):
            raise ValueError("Invalid bookmark timestamp or completion")
        incoming.append((key, row))
    # Pin order is a separate profile/server document. Empty orders are retained
    # as tombstones so an offline client cannot resurrect removed pins.
    pin_rows = body.get("pins", [])
    if not isinstance(pin_rows, list) or len(pin_rows) > 100:
        raise ValueError("Invalid pin orders")
    incoming_pins = {}
    for record in pin_rows:
        if not isinstance(record, dict):
            raise ValueError("Invalid pin order")
        scope = (record.get("serverId"), record.get("userId"))
        stamp = record.get("updatedAt")
        ids = record.get("playlistIds")
        if (
            not any(key[:2] == scope for key in allowed)
            or type(stamp) is not int
            or not 0 < stamp <= now + 300000
            or not isinstance(ids, list)
            or len(ids) > 100
            or any(
                not isinstance(value, str) or (*scope, value) not in allowed
                for value in ids
            )
            or len(set(ids)) != len(ids)
            or scope in incoming_pins
        ):
            raise ValueError("Pin order outside scope")
        incoming_pins[scope] = dict(
            serverId=scope[0], userId=scope[1], updatedAt=stamp, playlistIds=ids
        )
    saved = state.setdefault("playlist_progress", {})
    for key, row in incoming:
        encoded = json.dumps(key)
        previous = saved.get(encoded)
        # Playback timestamps, not request arrival, resolve offline/retry conflicts.
        if previous is None or row["updatedAt"] > previous["updatedAt"]:
            saved[encoded] = row
    pin_store = state.setdefault("playlist_pins", {})
    for scope, record in incoming_pins.items():
        encoded = json.dumps(scope)
        previous = pin_store.get(encoded)
        if previous is None or record["updatedAt"] > previous["updatedAt"]:
            pin_store[encoded] = record
    return {
        "schema": 1,
        "pins": [
            dict(
                record,
                playlistIds=[
                    value
                    for value in record["playlistIds"]
                    if (record["serverId"], record["userId"], value) in allowed
                ],
            )
            for record in pin_store.values()
            if any(key[:2] == (record["serverId"], record["userId"]) for key in allowed)
        ],
        "items": [
            row
            for row in saved.values()
            if tuple(row[k] for k in ("serverId", "userId", "playlistId")) in allowed
        ],
    }


def poster_exchange(state, body, directory):
    """Exchange one profile-scoped poster. Image bytes stay outside state.json."""
    scope = body.get("scope")
    # Reuse strict scope validation without creating bookmark records.
    merge(state, {"scopes": [scope], "items": []})
    key = json.dumps([scope[k] for k in ("serverId", "userId", "playlistId")])
    upload = body.get("upload")
    records = state.get("playlist_shared_posters", {})
    previous = records.get(key)
    root = Path(directory) / "companion-posters"
    if upload is not None:
        if not isinstance(upload, dict):
            raise ValueError("Invalid poster")
        stamp = upload.get("updatedAt")
        if type(stamp) is not int or not 0 < stamp <= int(time.time() * 1000) + 300000:
            raise ValueError("Invalid poster timestamp")
        mime = upload.get("mime")
        encoded = upload.get("data")
        if not isinstance(encoded, str) or len(encoded) > 7000000:
            raise ValueError("Poster too large")
        raw = base64.b64decode(encoded, validate=True)
        valid = {
            "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
            "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
            "image/gif": raw[:6] in (b"GIF87a", b"GIF89a"),
        }
        if not valid.get(mime) or not 0 < len(raw) <= 5000000:
            raise ValueError("Invalid poster image")
        revision = hashlib.sha256(raw).hexdigest()
        if previous is None or stamp > previous["updatedAt"]:
            root.mkdir(parents=True, exist_ok=True)
            target = root / revision
            if target.is_symlink():
                raise ValueError("Invalid poster path")
            if not target.exists():
                target.write_bytes(raw)
            previous = dict(revision=revision, mime=mime, updatedAt=stamp)
            state.setdefault("playlist_shared_posters", {})[key] = previous
    result = {"schema": 1, "poster": None}
    if previous and previous["revision"] != body.get("revision"):
        target = root / previous["revision"]
        if target.is_file() and not target.is_symlink():
            result["poster"] = dict(
                previous, data=base64.b64encode(target.read_bytes()).decode()
            )
    return result
