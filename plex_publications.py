# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only Plex publication snapshots and occurrence-aware change previews.

Only targets previously created by this application are eligible. Never infer
ownership from a matching playlist title. Remote writes stay in app.py.
"""
import hashlib
import json
from collections import Counter

import list_updates
import saved_lists


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def baseline(entry, settings):
    cfg = settings.get("plex", {})
    return digest(
        [
            list_updates.fingerprint(entry),
            entry.get("playlist"),
            saved_lists.publication_poster(entry),
            cfg,
        ]
    )


def target(entry, settings, remote):
    cfg = settings.get("plex", {})
    saved = entry.get("playlist") or {}
    key = str(saved.get("key", ""))
    if saved.get("server") != cfg.get("url") or not key.isdigit():
        raise ValueError(
            "Create a playlist on this Plex server first. Only saved Listweavarr targets can be updated."
        )
    identity = remote(cfg["url"], "/", cfg["key"], plex=True).get("machineIdentifier")
    if not identity:
        raise ValueError("Plex did not return its server identity.")
    metadata = remote(cfg["url"], "/playlists/" + key, cfg["key"], plex=True).find(
        "Playlist"
    )
    if metadata is None or metadata.get("title") != saved.get("title"):
        raise ValueError(
            "The saved playlist was removed or renamed in Plex. Recreate it explicitly rather than overwriting another target."
        )
    keys, start = [], 0
    while True:
        tree = remote(
            cfg["url"],
            f"/playlists/{key}/items?X-Plex-Container-Start={start}&X-Plex-Container-Size=500",
            cfg["key"],
            plex=True,
        )
        nodes = tree.findall("Video")
        if not nodes and start < int(tree.get("totalSize", start)):
            raise ValueError(
                "Plex returned an incomplete playlist. Retry before updating."
            )
        keys.extend(node.get("ratingKey") for node in nodes)
        start += len(nodes)
        if start >= int(tree.get("totalSize", start)):
            break
        if start > 100000:
            raise ValueError("This playlist exceeds the managed publication limit.")
    if any(not str(key).isdigit() for key in keys):
        raise ValueError("Plex returned an invalid playlist item.")
    return {
        "key": key,
        "title": metadata.get("title"),
        "machine": identity,
        "keys": keys,
    }


def changes(before, after):
    old, new = Counter(before), Counter(after)
    # Duplicate occurrences are meaningful in a curated watch order.
    retained_old, retained_new = [], []
    seen = Counter()
    for key in before:
        seen[key] += 1
        if seen[key] <= new[key]:
            retained_old.append((key, seen[key]))
    seen.clear()
    for key in after:
        seen[key] += 1
        if seen[key] <= old[key]:
            retained_new.append((key, seen[key]))
    return {
        "added": sum((new - old).values()),
        "removed": sum((old - new).values()),
        "reordered": retained_old != retained_new,
        "before_count": len(before),
        "after_count": len(after),
    }
