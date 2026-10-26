# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit local authoring command. Export curated lists without private state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import json
from pathlib import Path
import app
import list_sharing
import official_lists


def publish(state, previous):
    old = {row["id"]: row for row in previous.get("lists", [])}
    rows = []
    for entry in state["lists"]:
        identifier = entry.get("official_id") or "curated-" + entry["id"]
        data = list_sharing.export(entry)["list"]
        data["id"] = identifier
        data["updated_at"] = entry.get("updated_at", 0)
        before = old.get(identifier)
        unchanged = (
            before and {k: v for k, v in before.items() if k != "version"} == data
        )
        data["version"] = (
            before["version"] if unchanged else (before or {}).get("version", 0) + 1
        )
        rows.append(data)
    changed = rows != previous.get("lists", [])
    return {
        "format": "reelcheck-official-catalogue",
        "version": previous.get("version", 0) + int(changed),
        "lists": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promote-current-lists", action="store_true", required=True)
    args = parser.parse_args()
    state = app.read_state()
    previous = official_lists.document()
    data = publish(state, previous)
    official_lists.ROOT.mkdir(exist_ok=True)
    target = official_lists.ROOT / "official-lists.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(target)
    import catalogue_feed

    (official_lists.ROOT / "official-lists.manifest.json").write_text(
        json.dumps(
            catalogue_feed.manifest(data), ensure_ascii=False, separators=(",", ":")
        ),
        encoding="utf-8",
    )
    # Preserve every working list and its history, but classify authoring originals
    # under Official Lists instead of presenting them twice in the catalogue.
    for entry, row in zip(state["lists"], data["lists"]):
        entry.update(
            official_id=row["id"],
            official_version=row["version"],
            official_authoring=True,
        )
    app.save_state(state)
    print(
        "Published",
        len(data["lists"]),
        "official lists; catalogue version",
        data["version"],
    )


if __name__ == "__main__":
    main()
