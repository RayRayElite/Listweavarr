# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only provider/Plex workflow checks. Never saves lists or submits media/playlist writes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collections
import csv
import io
import json
from pathlib import Path

import app
import providers


def main():
    state = app.read_state()
    settings = state["settings"]
    # Exact episode IMDb ID comes from the episode's own external IDs, not its parent.
    episode_ids = providers.cached_tmdb(
        "tv/1403/season/1/episode/1/external_ids", settings
    )
    series_ids = providers.cached_tmdb("tv/1403/external_ids", settings)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Position", "Const", "Title", "Title Type", "Year"])
    writer.writerow(
        [3, series_ids["imdb_id"], "Agents of S.H.I.E.L.D.", "TV Series", 2013]
    )
    writer.writerow([2, episode_ids["imdb_id"], "Pilot", "TV Episode", 2013])
    writer.writerow([1, "tt0371746", "Iron Man", "Movie", 2008])
    mixed = app.import_items(stream.getvalue(), "csv", settings)
    assert [r["type"] for r in mixed] == ["movie", "episode", "show"]
    assert (
        mixed[1]["show_tmdb"] == "1403"
        and mixed[1]["season"] == "1"
        and mixed[1]["episode"] == "1"
    )
    compared = app.compare(mixed, settings)
    plan = app.playlist_preview({"name": "Verification only", "items": compared})
    assert plan["keys"] == [
        key
        for row in compared
        for key in (
            row.get("plex_keys", [])
            if row["status"] in ("available", "partial")
            else []
        )
    ]
    print(
        "IMDb-format mixed CSV: exact movie / episode / show IDs, positions and Plex expansion verified.",
        flush=True,
    )
    print(
        "Mixed comparison:",
        dict(collections.Counter(r["status"] for r in compared)),
        "| planned playable items:",
        plan["count"],
        flush=True,
    )
    for url in [
        "https://letterboxd.com/ben_vlbd/list/sony-spider-man-multiverse-spumc-ranking/",
        "https://letterboxd.com/mysteriis666/list/halloween/",
        "https://mdblist.com/lists/rip/marvel-cinematic-universe-mcu-in-universe-chronological-order",
        "https://chronocanon.com/franchise/pokemon-anime",
    ]:
        result = providers.import_url(url, lambda *a: None)
        print(
            "Provider verified:",
            result["name"],
            "| entries:",
            len(result["items"]),
            "| types:",
            dict(collections.Counter(r["type"] for r in result["items"])),
            "| warnings:",
            len(result["warnings"]),
            flush=True,
        )
        if "chronocanon.com" in url:
            assert len(result["items"]) == 47
            assert all(
                r.get("metadata_unresolved")
                for r in result["items"]
                if r["type"] == "season"
            )
    print(
        "Read-only checks complete: no lists saved, no downloads or Plex playlists submitted.",
        flush=True,
    )


if __name__ == "__main__":
    main()
