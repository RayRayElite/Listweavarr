# SPDX-License-Identifier: AGPL-3.0-only
"""Build and inspect a runtime archive from an explicit source allowlist.

Local data, old archives, provider captures, audits and private artwork never
enter this package. The public catalogue was independently scrubbed of artwork.
"""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def source_files(root=ROOT):
    files = list(root.glob("*.py"))
    files += [
        root / name
        for name in (
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "CHANGELOG.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "VERSION",
            "Start Listweavarr.cmd",
            "Start Listweavarr Curator.cmd",
            "Dockerfile",
            "compose.yaml",
            ".dockerignore",
            ".env.example",
        )
    ]
    for folder in ("web", "docs", "catalogue/bundled", "examples"):
        files.extend(
            p
            for p in (root / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )
    return sorted(files)


def main():
    version = (ROOT / "VERSION").read_text().strip()
    folder = ROOT / "releases"
    folder.mkdir(exist_ok=True)
    target = folder / ("Listweavarr-" + version + ".zip")
    files = source_files()
    for file in files:
        if file.suffix == ".py":
            compile(file.read_text(encoding="utf-8-sig"), str(file), "exec")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert all(
            not name.startswith(("data/", "audits/", "releases/", "Kometa Examples/"))
            for name in archive.namelist()
        )
        assert (
            "app.py" in archive.namelist() and "runtime_config.py" in archive.namelist()
        )
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(checksum + "  " + target.name + "\n")
    print(
        target.name,
        len(files),
        "files;",
        target.stat().st_size,
        "bytes; archive verified.",
    )


if __name__ == "__main__":
    main()
