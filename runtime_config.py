# SPDX-License-Identifier: AGPL-3.0-only
"""Deployment settings shared by the server, caches and Docker entry point.

Keep configuration reads here so local installs and containers use the same paths.
Defaults preserve existing installations; credentials belong only in the data dir.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DATA_DIR = (
    Path(os.environ.get("LISTWEAVARR_DATA_DIR", str(ROOT / "data")))
    .expanduser()
    .resolve()
)


def server_options():
    """Validate deployment settings before opening a socket or starting jobs."""
    host = os.environ.get("LISTWEAVARR_HOST", "127.0.0.1")
    port = int(os.environ.get("LISTWEAVARR_PORT", "8765"))
    if not 1 <= port <= 65535:
        raise ValueError("LISTWEAVARR_PORT must be between 1 and 65535.")
    public_url = os.environ.get(
        "LISTWEAVARR_PUBLIC_URL", f"http://127.0.0.1:{port}"
    ).rstrip("/")
    parsed = urlsplit(public_url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "LISTWEAVARR_PUBLIC_URL must be an HTTP(S) origin without a path or credentials."
        )
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}", parsed.netloc}
    allowed.update(
        v.strip()
        for v in os.environ.get("LISTWEAVARR_ALLOWED_HOSTS", "").split(",")
        if v.strip()
    )
    if any("*" in v or "/" in v or "@" in v for v in allowed):
        raise ValueError(
            "Allowed hosts must be explicit host[:port] values; wildcards are not accepted."
        )
    return {
        "host": host,
        "port": port,
        "public_url": public_url,
        "allowed_hosts": allowed,
        "open_browser": os.environ.get("LISTWEAVARR_OPEN_BROWSER", "1").lower()
        not in ("0", "false", "no"),
    }


def curator_enabled():
    """Local authoring switch, not remote curator authentication (see docs)."""
    return (
        os.environ.get(
            "LISTWEAVARR_CURATOR_MODE", os.environ.get("REELCHECK_CURATOR_MODE", "0")
        )
        == "1"
    )
