# SPDX-License-Identifier: AGPL-3.0-only
"""Version-checked local loader probe, with exact rollback. Never downloads Plex.

Run status/install/uninstall against the installed web-client directory. Install
and uninstall require Plex to be closed and may require Windows elevation.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

SOURCE = Path(__file__).resolve().parent
KNOWN_INDEX = "d81687f1b5710890c3be9681236e8f92c39e9d48399f82a80dd67963297b92b7"
ASSETS = {
    "layout.js": "listweavarr-playlist-layout.js",
    "bookmarks.js": "listweavarr-playlist-bookmarks.js",
    "plex-adapter.js": "listweavarr-playlist-adapter.js",
    "artwork.js": "listweavarr-playlist-artwork.js",
    "settings.js": "listweavarr-playlist-settings.js",
    "home.js": "listweavarr-playlist-home.js",
    "runtime.js": "listweavarr-playlist-runtime.js",
}
BACKUP = "index.html.listweavarr-original"
STATE = "listweavarr-playlist-install.json"
MARKUP = b'\n<!-- Listweavarr playlist companion v1 -->\n<script src="listweavarr-playlist-bookmarks.js"></script>\n<script src="listweavarr-playlist-adapter.js"></script>\n<script src="listweavarr-playlist-artwork.js"></script>\n<script src="listweavarr-playlist-settings.js"></script>\n<script src="listweavarr-playlist-home.js"></script>\n<script src="listweavarr-playlist-runtime.js"></script>\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plex_running():
    if os.name != "nt":
        raise ValueError("The desktop installer is Windows-only.")
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Plex.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=True,
    )
    return any(
        row and row[0].lower() == "plex.exe"
        for row in csv.reader(io.StringIO(result.stdout))
    )


def atomic_write(path, data):
    temporary = path.with_name(path.name + ".listweavarr-tmp")
    if temporary.exists():
        raise ValueError("Previous temporary write exists; inspect it before retrying.")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def inspect(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose the installed web-client directory.")
    root = root.resolve(strict=True)
    for name in ["index.html", BACKUP, STATE, *ASSETS.values()]:
        if (root / name).is_symlink():
            raise ValueError("Refusing a symlink in the installation target.")
    data = (root / "index.html").read_bytes()
    state_path = root / STATE
    if not state_path.exists():
        return root, data, None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("original_sha256") != KNOWN_INDEX or digest(data) != state.get(
        "patched_sha256"
    ):
        raise ValueError(
            "Plex files changed since installation. Do not overwrite an update; inspect before repair."
        )
    if digest((root / BACKUP).read_bytes()) != KNOWN_INDEX:
        raise ValueError("Original backup failed verification.")
    if not state.get("assets") or set(state["assets"]) - set(ASSETS.values()):
        raise ValueError("Unknown companion asset manifest.")
    for name in state["assets"]:
        if digest((root / name).read_bytes()) != state.get("assets", {}).get(name):
            raise ValueError("Companion asset changed; refusing destructive rollback.")
    return root, data, state


def patched_index(data):
    position = data.find(b'<script src="js/main-')
    if position < 0:
        position = data.find(b"</body>")
    value = (
        data[:position]
        + b'<script src="listweavarr-playlist-layout.js"></script>\n'
        + data[position:]
    )
    return value.replace(b"</body>", MARKUP + b"</body>")


def diagnose(root):
    """Read-only status remains useful after Plex replaces its entry point."""
    root = Path(root)
    try:
        path, data, state = inspect(root)
        return {
            "installed": bool(state),
            "supported": bool(state) or digest(data) == KNOWN_INDEX,
            "status": (
                "installed"
                if state
                else "ready" if digest(data) == KNOWN_INDEX else "unsupported"
            ),
            "index_sha256": digest(data),
        }
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return {
            "installed": False,
            "supported": False,
            "status": "needs-review",
            "message": str(error),
        }


def recover(root):
    """Remove verified stale assets after Plex updates; NEVER restore an old index
    over a new Plex version. Unknown new versions stay clean and unsupported.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or plex_running():
        raise ValueError("Close Plex and select its real web-client directory.")
    root = root.resolve(strict=True)
    names = ["index.html", BACKUP, STATE, *ASSETS.values()]
    if any((root / name).is_symlink() for name in names):
        raise ValueError("Refusing a symlink in the installation target.")
    state = json.loads((root / STATE).read_text(encoding="utf-8"))
    data = (root / "index.html").read_bytes()
    if (
        state.get("original_sha256") != KNOWN_INDEX
        or digest((root / BACKUP).read_bytes()) != KNOWN_INDEX
    ):
        raise ValueError("Original backup failed verification.")
    assets = state.get("assets", {})
    if not assets or set(assets) - set(ASSETS.values()):
        raise ValueError("Unknown companion asset manifest.")
    if b"listweavarr-" in data.lower() or digest(data) == state.get("patched_sha256"):
        raise ValueError(
            "The entry point still contains companion changes. Use uninstall or inspect it manually."
        )
    for name, expected in assets.items():
        if (root / name).exists() and digest((root / name).read_bytes()) != expected:
            raise ValueError("Companion asset changed; refusing cleanup.")
    for name in assets:
        (root / name).unlink(missing_ok=True)
    (root / STATE).unlink()
    (root / BACKUP).unlink()
    return {
        "installed": False,
        "new_plex_index_preserved": True,
        "supported": digest(data) == KNOWN_INDEX,
    }


def operate(root, action):
    if action == "status":
        return diagnose(root)
    if action == "recover":
        return recover(root)
    root, data, state = inspect(root)
    if action not in ("install", "uninstall", "update"):
        raise ValueError("Unsupported action")
    if plex_running():
        raise ValueError(
            "Close Plex before changing its client files. No changes made."
        )
    if action == "uninstall":
        if not state:
            return {"installed": False, "changed": False}
        atomic_write(root / "index.html", (root / BACKUP).read_bytes())
        for name in state["assets"]:
            (root / name).unlink()
        (root / STATE).unlink()
        (root / BACKUP).unlink()
        return {"installed": False, "restored_original": True}
    if state:
        if action != "update":
            return {"installed": True, "changed": False}
        assets = {
            target: (SOURCE / source).read_bytes() for source, target in ASSETS.items()
        }
        patched = patched_index((root / BACKUP).read_bytes())
        updated = {
            **state,
            "patched_sha256": digest(patched),
            "assets": {name: digest(raw) for name, raw in assets.items()},
        }
        writes = {
            **assets,
            "index.html": patched,
            STATE: json.dumps(updated, indent=2).encode(),
        }
        previous = {
            name: (root / name).read_bytes() if (root / name).exists() else None
            for name in writes
        }
        written = []
        try:
            for name, raw in writes.items():
                atomic_write(root / name, raw)
                written.append(name)
        except Exception:
            for name in reversed(written):
                if previous[name] is None:
                    (root / name).unlink()
                else:
                    atomic_write(root / name, previous[name])
            raise
        return {"installed": True, "updated": True, "backup_verified": True}
    if digest(data) != KNOWN_INDEX or data.count(b"</body>") != 1:
        raise ValueError("Unsupported Plex client version. No changes made.")
    for name in [BACKUP, *ASSETS.values()]:
        if (root / name).exists():
            raise ValueError(
                "A backup or companion file already exists. Inspect before installing."
            )
    assets = {
        target: (SOURCE / source).read_bytes() for source, target in ASSETS.items()
    }
    # Load the metric adapter before Plex imports its layout functions. Appending
    # CSS after startup would leave virtualized rows at their old square height.
    patched = patched_index(data)
    state = {
        "schema": 1,
        "original_sha256": KNOWN_INDEX,
        "patched_sha256": digest(patched),
        "assets": {name: digest(value) for name, value in assets.items()},
    }
    # Keep the original before changing the entry point. On a partial install,
    # restore only our known writes; never delete an unrelated target directory.
    written = []
    try:
        for name, value in {
            BACKUP: data,
            **assets,
            STATE: json.dumps(state, indent=2).encode("utf-8"),
        }.items():
            atomic_write(root / name, value)
            written.append(name)
        atomic_write(root / "index.html", patched)
    except Exception:
        for name in reversed(written):
            (root / name).unlink()
        raise
    return {
        "installed": True,
        "mode": "development-adapter",
        "backup_verified": digest((root / BACKUP).read_bytes()) == KNOWN_INDEX,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["status", "install", "update", "uninstall", "recover"]
    )
    parser.add_argument(
        "--web-client", default=r"C:\Program Files\Plex\Plex\web-client"
    )
    args = parser.parse_args()
    try:
        print(json.dumps(operate(args.web_client, args.action)))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")
