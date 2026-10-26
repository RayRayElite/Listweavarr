# SPDX-License-Identifier: AGPL-3.0-only
"""Fail CI if the tracked source includes secrets, private state or artwork.

This is a conservative release-hygiene check, not a replacement for reviewing a
Git diff or for a dedicated server-side secret scanner. It never prints matches.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DENIED = ("data/", "audits/", "releases/", "Kometa Examples/", ".env", "tmp")
SECRET_PATTERNS = [
    rb"gh[pousr]_[A-Za-z0-9]{30,}",
    rb"github_pat_[A-Za-z0-9_]{30,}",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
]
PRIVATE_KEYS = {
    "settings",
    "plex_auth",
    "csrf",
    "plex_keys",
    "request_log",
    "requests",
    "watch_progress",
    "manager_monitor",
}


def validate_paths(paths):
    errors = []
    for name in paths:
        if name == ".env.example":
            continue
        if (
            name.startswith(DENIED)
            or "__pycache__/" in name
            or name.endswith((".pyc", ".bak", ".log"))
        ):
            errors.append("Private/generated path tracked: " + name)
    return errors


def validate_catalogue(path):
    document = json.loads(path.read_text(encoding="utf-8"))

    def visit(value):
        if isinstance(value, dict):
            if PRIVATE_KEYS.intersection(value):
                raise ValueError("Private state in public catalogue")
            if value.get("poster") or value.get("playlist_poster"):
                raise ValueError("Embedded artwork in public catalogue")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)


def main():
    names = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    paths = [name for name in names if name and (ROOT / name).is_file()]
    errors = validate_paths(paths)
    for name in paths:
        raw = (ROOT / name).read_bytes()
        if any(re.search(pattern, raw) for pattern in SECRET_PATTERNS):
            errors.append("Possible credential in " + name)
    try:
        validate_catalogue(ROOT / "catalogue/bundled/official-lists.json")
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    if errors:
        print("Release hygiene FAILED:")
        print("\n".join(errors))
        return 1
    print(
        "Release hygiene passed for",
        len(paths),
        "tracked files; private state and artwork excluded.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
