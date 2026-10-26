# SPDX-License-Identifier: AGPL-3.0-only
"""Browser-only TV poster status and optional network artwork.

Uses original shipped status assets or user-supplied overlays; it never changes Plex artwork or media files.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import datetime
import re
import os
import runtime_config
from pathlib import Path
import providers

_old = Path(__file__).resolve().parent / "Kometa Examples" / "overlays"
_private = runtime_config.DATA_DIR / "private-assets" / "kometa" / "overlays"
_legacy = _private if _private.exists() else _old
ASSETS = Path(
    os.environ.get(
        "LISTWEAVARR_OVERLAY_DIR",
        str(
            _legacy
            if _legacy.exists()
            else Path(__file__).resolve().parent / "web" / "assets" / "overlays"
        ),
    )
)


def asset_path(url):
    parts = url.split("/")
    if (
        len(parts) != 4
        or parts[1] != "poster-overlays"
        or parts[2] not in ("status-top-left", "network-top-left")
    ):
        return None
    name = parts[3]
    if (
        ":" in name
        or not name.endswith((".png", ".svg"))
        or name in (".", "..")
        or "/" in name
        or "\\" in name
    ):
        return None
    path = ASSETS / parts[2] / name
    return path if path.is_file() else None


def show_info(identifier, settings):
    if not str(identifier).isdigit():
        raise ValueError("An exact TV show TMDB ID is required.")
    data = providers.cached_tmdb("tv/" + str(identifier), settings)
    raw = data.get("status", "")
    status = {
        "Ended": "ended",
        "Canceled": "cancelled",
        "Cancelled": "cancelled",
        "Returning Series": "returning",
    }.get(raw)
    # Airing means an episode in TMDB's current seven-day broadcast window.
    today = datetime.date.today()
    if status == "returning":
        for key in ("last_episode_to_air", "next_episode_to_air"):
            try:
                air = datetime.date.fromisoformat(
                    (data.get(key) or {}).get("air_date", "")
                )
                if (
                    today - datetime.timedelta(days=3)
                    <= air
                    <= today + datetime.timedelta(days=3)
                ):
                    status = "airing"
            except (ValueError, TypeError):
                pass
    networks = [n.get("name") for n in data.get("networks", []) if n.get("name")]
    normalize = lambda name: re.sub(r"[^a-z0-9]", "", name.casefold())
    files = {
        normalize(p.stem): p.name for p in (ASSETS / "network-top-left").glob("*.png")
    }
    network = next(
        (files[normalize(n)] for n in networks if normalize(n) in files), None
    )
    return {
        "status": status,
        "status_label": status.capitalize() if status else raw or "Status unknown",
        "status_asset": next(
            (
                status + ext
                for ext in (".png", ".svg")
                if status and (ASSETS / "status-top-left" / (status + ext)).is_file()
            ),
            None,
        ),
        "network": networks[0] if networks else None,
        "network_asset": network,
    }
