# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only, revocable artwork capability for the optional Plex companion.

No Plex credentials, list contents or watched state cross this boundary. Pairing
is created through the application's existing CSRF-protected local UI.
"""
import base64
import hashlib
import ipaddress
import secrets
import urllib.parse
import saved_lists


def origins(state):
    url = urllib.parse.urlsplit(
        state.get("settings", {}).get("plex", {}).get("url", "")
    )
    allowed = {"null", "https://app.plex.tv"}
    if url.scheme in ("http", "https") and url.netloc:
        allowed.add(f"{url.scheme}://{url.netloc}")
        if (url.hostname or "").endswith(".plex.direct"):
            try:
                address = ipaddress.ip_address(
                    url.hostname.split(".")[0].replace("-", ".")
                )
                if (
                    address.version == 4
                    and address.is_private
                    and not address.is_loopback
                ):
                    for scheme in ("http", "https"):
                        allowed.add(f"{scheme}://{address}:{url.port or 32400}")
            except ValueError:
                pass
    return allowed


def authorize(state, authorization):
    pairing = state.get("playlist_artwork_pairing", {})
    token = pairing.get("token", "")
    supplied = (
        authorization.removeprefix("Bearer ")
        if authorization.startswith("Bearer ")
        else ""
    )
    return bool(
        isinstance(token, str)
        and token
        and len(supplied) < 200
        and secrets.compare_digest(token.encode(), supplied.encode())
    )


def entries(state):
    pairing = state.get("playlist_artwork_pairing", {})
    cfg = state.get("settings", {}).get("plex", {})
    if not pairing.get("machine") or pairing.get("server") != cfg.get("url"):
        return []
    result = {}
    for entry in state.get("lists", []):
        targets = [entry.get("playlist") or {}]
        targets += [
            {"key": row["playlistId"], "server": row["server"]}
            for row in state.get("playlist_artwork_mappings", [])
            if row.get("listId") == entry.get("id")
            and row.get("serverId") == pairing["machine"]
        ]
        image = entry.get("poster") or entry.get("playlist_poster")
        if not image:
            continue
        image = saved_lists.poster(image)
        for target in targets:
            key = str(target.get("key", ""))
            if target.get("server") == cfg.get("url") and key.isdigit():
                result[key] = {
                    "serverId": pairing["machine"],
                    "playlistId": key,
                    "revision": hashlib.sha256(image.encode()).hexdigest(),
                    "image": image,
                }
    return list(result.values())


def discover(state, machine, remote, preview):
    """Artwork association only, never authority to replace/delete a playlist.
    Reconcile older playlists by exact full ordered IDs, preserving duplicates.
    """
    cfg = state["settings"]["plex"]
    candidates = []
    for entry in state.get("lists", []):
        if not (entry.get("poster") or entry.get("playlist_poster")):
            continue
        keys = [str(key) for key in preview(entry)["keys"]]
        if keys:
            candidates.append((entry, keys))
    tree = remote(cfg["url"], "/playlists?playlistType=video", cfg["key"], plex=True)
    result = []
    for playlist in tree:
        key = playlist.get("ratingKey", "")
        count = int(playlist.get("leafCount", 0))
        possible = [(entry, keys) for entry, keys in candidates if len(keys) == count]
        if (
            not key.isdigit()
            or not possible
            or count > 10000
            or playlist.get("smart") == "1"
        ):
            continue
        actual = []
        while len(actual) < count:
            page = remote(
                cfg["url"],
                f"/playlists/{key}/items?X-Plex-Container-Start={len(actual)}&X-Plex-Container-Size=500",
                cfg["key"],
                plex=True,
            )
            rows = page.findall("Video")
            if not rows:
                break
            actual += [row.get("ratingKey") for row in rows]
        matches = [entry for entry, keys in possible if keys == actual]
        # Identical copies with identical artwork are harmless; competing artwork
        # choices require an explicit publication mapping rather than a guess.
        images = {
            entry.get("poster") or entry.get("playlist_poster") for entry in matches
        }
        if len(images) == 1:
            result.append(
                {
                    "listId": matches[0]["id"],
                    "serverId": machine,
                    "playlistId": key,
                    "server": cfg["url"],
                }
            )
    return result


def catalogue(state):
    return {
        "schema": 1,
        "items": [
            {k: v for k, v in row.items() if k != "image"} for row in entries(state)
        ],
    }


def image(state, machine, playlist):
    row = next(
        (
            row
            for row in entries(state)
            if row["serverId"] == machine and row["playlistId"] == playlist
        ),
        None,
    )
    if not row:
        raise ValueError("No matching Listweavarr playlist artwork.")
    header, value = row["image"].split(",", 1)
    return header[5:].split(";", 1)[0], base64.b64decode(value, validate=True)
