# SPDX-License-Identifier: AGPL-3.0-only
"""Reviewed native movie/show collection publication, separate from playlists.

Collections are unique members of one Plex library, not mixed episode watch
orders. Only exact saved target identities can be updated. Reads and pure plans
are reusable; all writes require the caller's single-use review and state guard.
API contracts were checked against Plex and Python-PlexAPI documentation.
"""
import hashlib
import json
import urllib.parse

import list_updates


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def baseline(entry, settings):
    return digest(
        [
            list_updates.fingerprint(entry),
            entry.get("poster"),
            entry.get("plex_collection"),
            settings.get("plex"),
        ]
    )


def kind(entry):
    kinds = {r.get("type") for r in entry["items"]}
    if len(kinds) != 1 or not kinds <= {"movie", "show"}:
        raise ValueError(
            "Native collections require a movie-only or whole-show-only list. Use a Plex playlist for mixed titles, seasons or episodes."
        )
    return next(iter(kinds))


def libraries(settings, remote):
    cfg = settings["plex"]
    return [
        {"id": r.get("key"), "title": r.get("title"), "type": r.get("type")}
        for r in remote(cfg["url"], "/library/sections", cfg["key"], plex=True).findall(
            "Directory"
        )
        if r.get("type") in ("movie", "show") and str(r.get("key", "")).isdigit()
    ]


def members(key, cfg, remote):
    keys, start = [], 0
    while True:
        tree = remote(
            cfg["url"],
            f"/library/collections/{key}/children?X-Plex-Container-Start={start}&X-Plex-Container-Size=500",
            cfg["key"],
            plex=True,
        )
        nodes = [n for n in tree if n.tag in ("Video", "Directory")]
        if not nodes and start < int(tree.get("totalSize", start)):
            raise ValueError("Plex returned an incomplete collection; preview again.")
        keys.extend(n.get("ratingKey") for n in nodes)
        start += len(nodes)
        if start > 10000 or any(not str(k or "").isdigit() for k in keys):
            raise ValueError("Invalid or oversized Plex collection.")
        if tree.get("totalSize") is not None:
            if start >= int(tree.get("totalSize")):
                break
        elif len(nodes) < 500:
            break
    if len(set(keys)) != len(keys):
        raise ValueError(
            "Plex returned repeated collection members; inspect it before updating."
        )
    return keys


def target(saved, settings, remote):
    cfg = settings["plex"]
    if saved.get("server") != cfg["url"] or not str(saved.get("key", "")).isdigit():
        raise ValueError("This saved collection belongs to another Plex server.")
    machine = remote(cfg["url"], "/", cfg["key"], plex=True).get("machineIdentifier")
    if not machine or machine != saved.get("machine"):
        raise ValueError(
            "The Plex server identity changed; the collection will not be modified."
        )
    tree = remote(
        cfg["url"], f'/library/collections/{saved["key"]}', cfg["key"], plex=True
    )
    row = tree.find("Directory")
    if (
        row is None
        or row.get("type") != "collection"
        or row.get("smart", "0") not in ("0", "false")
    ):
        raise ValueError(
            "The saved manual collection is unavailable or became a smart collection."
        )
    section = row.get("librarySectionID") or tree.get("librarySectionID")
    if (
        row.get("title") != saved.get("title")
        or str(section) != str(saved.get("section"))
        or row.get("guid") != saved.get("guid")
        or row.get("subtype") != saved.get("kind")
    ):
        raise ValueError(
            "The saved collection was renamed, replaced or moved. It will not be overwritten."
        )
    return {
        **{
            k: saved[k]
            for k in ("key", "title", "section", "kind", "guid", "machine", "server")
        },
        "keys": members(saved["key"], cfg, remote),
        "sort": row.get("collectionSort"),
        "thumb": row.get("thumb"),
    }


def plan(entry, catalog, section, match_item, server=""):
    media = kind(entry)
    if section["type"] != media:
        raise ValueError("Choose a library matching this list's media type.")
    scoped = [r for r in catalog if str(r.get("library_id")) == str(section["id"])]
    keys, seen, rows = [], set(), []
    for item in entry["items"]:
        if item.get("metadata_unresolved"):
            matches, basis = [], "unresolved identity"
        elif (
            item.get("plex_override")
            and item.get("plex_server") == server
            and any(
                r.get("key") == item["plex_override"] and r.get("type") == media
                for r in scoped
            )
        ):
            matches = [r for r in scoped if r.get("key") == item["plex_override"]]
            basis = "confirmed manually"
        else:
            matches, basis = match_item(item, scoped)
        key = (
            matches[0].get("key")
            if len(matches) == 1 and basis in ("provider ID", "confirmed manually")
            else None
        )
        if key and not str(key).isdigit():
            raise ValueError("Plex returned an invalid collection member.")
        included = bool(key and key not in seen)
        if included:
            keys.append(key)
            seen.add(key)
        rows.append(
            {
                "title": item["title"],
                "key": key,
                "included": included,
                "reason": (
                    "Included"
                    if included
                    else (
                        "Already included once"
                        if key
                        else "Not uniquely confirmed in this library"
                    )
                ),
            }
        )
    if len(keys) > 10000:
        raise ValueError("A managed collection supports at most 10,000 members.")
    return {
        "keys": keys,
        "entries": rows,
        "kind": media,
        "section": str(section["id"]),
        "omitted": sum(not r["key"] for r in rows),
        "deduplicated": sum(bool(r["key"]) and not r["included"] for r in rows),
    }


def name_available(title, section, cfg, remote):
    start = 0
    while True:
        tree = remote(
            cfg["url"],
            f"/library/sections/{section}/collections?X-Plex-Container-Start={start}&X-Plex-Container-Size=500",
            cfg["key"],
            plex=True,
        )
        nodes = tree.findall("Directory")
        if any(n.get("title", "").casefold() == title.casefold() for n in nodes):
            raise ValueError(
                "A collection with this name already exists. Choose another name; existing collections are never adopted by name."
            )
        start += len(nodes)
        if start > 10000:
            raise ValueError("Too many collections to safely check names.")
        if tree.get("totalSize") is not None:
            total = int(tree.get("totalSize"))
            if not nodes and start < total:
                raise ValueError("Plex returned an incomplete collection catalogue.")
            if start >= total:
                break
        elif len(nodes) < 500:
            break


def apply(proposal, entry, settings, remote, guard, checkpoint, upload):
    """Apply a reviewed plan; checkpoint target identity before further writes.

    Collection APIs are not transactional. A failed update retains the collection
    and its identity for a new diff; no automatic retries, deletion or rollback.
    DELETE below removes collection membership only, never a media file.
    """
    cfg = settings["plex"]
    keys = proposal["desired"]["keys"]
    if not keys:
        raise ValueError("No confirmed members in this library; nothing was changed.")
    guard()
    before = proposal.get("target")
    saved = entry.get("plex_collection")
    if before:
        if target(saved, settings, remote) != before:
            raise ValueError(
                "The Plex collection changed after preview. Preview again before updating."
            )
        key, machine = before["key"], before["machine"]
        checkpoint(before)
    else:
        name_available(proposal["title"], proposal["desired"]["section"], cfg, remote)
        machine = remote(cfg["url"], "/", cfg["key"], plex=True).get(
            "machineIdentifier"
        )
        if not machine:
            raise ValueError("Plex did not return its server identity.")
        uri = f"server://{machine}/com.plexapp.plugins.library/library/metadata/"
        query = urllib.parse.urlencode(
            {
                "title": proposal["title"],
                "sectionId": proposal["desired"]["section"],
                "type": 1 if proposal["desired"]["kind"] == "movie" else 2,
                "smart": 0,
                "uri": uri + ",".join(keys[:100]),
            }
        )
        tree = remote(
            cfg["url"],
            "/library/collections?" + query,
            cfg["key"],
            method="POST",
            plex=True,
        )
        row = tree.find("Directory")
        if (
            row is None
            or not str(row.get("ratingKey", "")).isdigit()
            or not row.get("guid")
        ):
            raise ValueError(
                "Plex may have created the collection but did not confirm its identity. Check Plex before retrying."
            )
        key = row.get("ratingKey")
        saved = {
            "key": key,
            "title": proposal["title"],
            "section": proposal["desired"]["section"],
            "kind": proposal["desired"]["kind"],
            "guid": row.get("guid"),
            "machine": machine,
            "server": cfg["url"],
        }
        checkpoint(saved)
        before = target(saved, settings, remote)
    uri = f"server://{machine}/com.plexapp.plugins.library/library/metadata/"
    additions = [k for k in keys if k not in before["keys"]]
    for start in range(0, len(additions), 100):
        guard()
        query = urllib.parse.urlencode(
            {"uri": uri + ",".join(additions[start : start + 100])}
        )
        remote(
            cfg["url"],
            f"/library/collections/{key}/items?" + query,
            cfg["key"],
            method="PUT",
            plex=True,
        )
    for removed in before["keys"]:
        if removed not in keys:
            guard()
            remote(
                cfg["url"],
                f"/library/collections/{key}/items/{removed}",
                cfg["key"],
                method="DELETE",
                plex=True,
            )
    guard()
    remote(
        cfg["url"],
        f"/library/metadata/{key}/prefs?collectionSort=2",
        cfg["key"],
        method="PUT",
        plex=True,
    )
    current = members(key, cfg, remote)
    for position, member in enumerate(keys):
        if position >= len(current) or current[position] != member:
            guard()
            path = f"/library/collections/{key}/items/{member}/move" + (
                "?after=" + keys[position - 1] if position else ""
            )
            remote(cfg["url"], path, cfg["key"], method="PUT", plex=True)
            if member in current:
                current.remove(member)
            current.insert(position, member)
    if members(key, cfg, remote) != keys:
        raise ValueError(
            "The collection was changed but its final order could not be verified. It is retained; preview a fresh diff before retrying."
        )
    warning = ""
    if entry.get("poster"):
        try:
            upload(key, entry["poster"], cfg)
        except ValueError:
            warning = "Collection saved; Plex did not confirm its poster. Review again to retry artwork."
    return {
        **saved,
        "keys": keys,
        "count": len(keys),
        "fingerprint": digest([keys, entry.get("poster")]),
        "warning": warning,
    }
