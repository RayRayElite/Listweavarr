# SPDX-License-Identifier: AGPL-3.0-only
"""Package only original companion source, never Plex code or private artwork."""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "layout.js",
    "bookmarks.js",
    "plex-adapter.js",
    "artwork.js",
    "settings.js",
    "home.js",
    "runtime.js",
    "manifest.json",
    "background.js",
    "options.html",
    "options.css",
    "options.js",
    "desktop.py",
    "setup.ps1",
    "Setup Playlist Companion.cmd",
    "Start Plex without Companion.cmd",
    "README.md",
)
BROWSER_FILES = tuple(
    name for name in FILES if name.endswith((".js", ".json", ".html", ".css"))
)


def browser_folder(source, output):
    """Keep Chrome's load-unpacked root separate from Python's bytecode cache."""
    output.mkdir(parents=True, exist_ok=True)
    allowed = set(BROWSER_FILES) | {"LICENSE"}
    if any(
        path.name not in allowed or not path.is_file() or path.is_symlink()
        for path in output.iterdir()
    ):
        raise ValueError(
            "Unexpected files in the browser build folder; inspect it before rebuilding."
        )
    for name in BROWSER_FILES:
        (output / name).write_bytes((source / name).read_bytes())
    (output / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
    return output


def main():
    folder = ROOT / "integrations/plex-playlist-companion"
    output = ROOT / "releases/Listweavarr-Playlist-Companion-0.4.0.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(folder / name, name)
        archive.write(ROOT / "LICENSE", "LICENSE")
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(FILES) | {"LICENSE"}
    output.with_suffix(".zip.sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n"
    )
    browser = browser_folder(folder, ROOT / "releases/Playlist-Companion-Chrome")
    browser_zip = output.with_name("Listweavarr-Playlist-Companion-Chrome-0.4.0.zip")
    with zipfile.ZipFile(browser_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in (*BROWSER_FILES, "LICENSE"):
            archive.write(browser / name, name)
    with zipfile.ZipFile(browser_zip) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(BROWSER_FILES) | {"LICENSE"}
    browser_zip.with_suffix(".zip.sha256").write_text(
        hashlib.sha256(browser_zip.read_bytes()).hexdigest()
        + "  "
        + browser_zip.name
        + "\n"
    )
    print(output.name, "verified; original companion source only")
    print("Browser-only load-unpacked folder:", browser)


if __name__ == "__main__":
    main()
