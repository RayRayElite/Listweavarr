# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only live checks using locally saved connections; never prints credentials."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import trakt_features

state = app.read_state()
settings = state["settings"]
result = trakt_features.search_lists(settings, "Marvel chronological")
print("Public list search:", len(result["lists"]), "results")
details = trakt_features.title_features(settings, {"type": "movie", "tmdb": "1726"})
print(
    "Iron Man:",
    details["rating"],
    "Trakt rating;",
    len(details["lists"]),
    "curated lists;",
    len(details["recommendations"]),
    "recommendations",
)
calendar = app.release_calendar(state)
print("Followed-list calendar:", len(calendar["items"]), "upcoming releases")
entry = next(
    (l for l in state["lists"] if "trakt.tv/" in (l.get("source") or "")), None
)
if entry:
    checked = trakt_features.check_source(entry, settings)
    print(
        "Followed source:",
        checked["saved_count"],
        "saved;",
        checked["count"],
        "on Trakt; changed:",
        checked["changed"],
    )
    progress = app.watch_progress(entry, settings)
    print(
        "Plex progress:",
        progress["completed"],
        "/",
        progress["entries"],
        "entries watched",
    )
