# SPDX-License-Identifier: AGPL-3.0-only
"""Prepare/check the public update manifest; never read the private workspace.

Curators export and review an artwork-free catalogue into catalogue/bundled,
then run this command and commit both files in one change. --check is read-only
and runs in CI so consumers never see a knowingly stale manifest in a release.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
import catalogue_feed
from scripts.check_release import validate_catalogue


def prepare(folder, check=False):
    source = folder / "official-lists.json"
    validate_catalogue(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    catalogue_feed.validate(document, app.normalize)
    expected = catalogue_feed.manifest(document)
    target = folder / "official-lists.manifest.json"
    if check:
        if not target.exists() or json.loads(target.read_text("utf-8")) != expected:
            raise ValueError(
                "Catalogue manifest is stale. Run scripts/prepare_catalogue_feed.py."
            )
    else:
        target.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return len(expected["lists"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(
        "Public catalogue verified:",
        prepare(ROOT / "catalogue/bundled", args.check),
        "lists",
    )
