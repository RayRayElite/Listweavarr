# SPDX-License-Identifier: AGPL-3.0-only
"""Small, capability-scoped bookmark store; never changes Plex watch history."""
import hmac
import json
import time


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
            or type(row.get("completed")) is not bool
        ):
            raise ValueError("Invalid bookmark timestamp or completion")
        incoming.append((key, row))
    saved = state.setdefault("playlist_progress", {})
    for key, row in incoming:
        encoded = json.dumps(key)
        previous = saved.get(encoded)
        # Playback timestamps, not request arrival, resolve offline/retry conflicts.
        if previous is None or row["updatedAt"] > previous["updatedAt"]:
            saved[encoded] = row
    return {
        "schema": 1,
        "items": [
            row
            for row in saved.values()
            if tuple(row[k] for k in ("serverId", "userId", "playlistId")) in allowed
        ],
    }
