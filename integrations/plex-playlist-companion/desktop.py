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
    "bookmarks.js": "listweavarr-playlist-bookmarks.js",
    "runtime.js": "listweavarr-playlist-runtime.js",
}
BACKUP = "index.html.listweavarr-original"
STATE = "listweavarr-playlist-install.json"
MARKUP = b'\n<!-- Listweavarr playlist companion probe v1 -->\n<script src="listweavarr-playlist-bookmarks.js"></script>\n<script src="listweavarr-playlist-runtime.js"></script>\n'


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
    for name in ASSETS.values():
        if digest((root / name).read_bytes()) != state.get("assets", {}).get(name):
            raise ValueError("Companion asset changed; refusing destructive rollback.")
    return root, data, state


def operate(root, action):
    root, data, state = inspect(root)
    if action == "status":
        return {
            "installed": state is not None,
            "supported": state is not None or digest(data) == KNOWN_INDEX,
            "index_sha256": digest(data),
        }
    if action not in ("install", "uninstall"):
        raise ValueError("Unsupported action")
    if plex_running():
        raise ValueError(
            "Close Plex before changing its client files. No changes made."
        )
    if action == "uninstall":
        if not state:
            return {"installed": False, "changed": False}
        atomic_write(root / "index.html", (root / BACKUP).read_bytes())
        for name in ASSETS.values():
            (root / name).unlink()
        (root / STATE).unlink()
        (root / BACKUP).unlink()
        return {"installed": False, "restored_original": True}
    if state:
        return {"installed": True, "changed": False}
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
    patched = data.replace(b"</body>", MARKUP + b"</body>")
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
        "mode": "bootstrap-probe",
        "backup_verified": digest((root / BACKUP).read_bytes()) == KNOWN_INDEX,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "install", "uninstall"])
    parser.add_argument(
        "--web-client", default=r"C:\Program Files\Plex\Plex\web-client"
    )
    args = parser.parse_args()
    try:
        print(json.dumps(operate(args.web_client, args.action)))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")
