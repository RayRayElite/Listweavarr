# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only checks for TV metadata and full-show Plex coverage."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from concurrent.futures import ThreadPoolExecutor
import app
import providers


if __name__ == "__main__":
    state = app.read_state()
    rows = [i for l in state["lists"] for i in l["items"] if i["type"] != "movie"]

    def check(row):
        try:
            details = providers.title_details(row, state["settings"])
            return (
                row["title"],
                bool(details["poster"]),
                bool(details["overview"]),
                None,
            )
        except Exception as exc:
            return row["title"], False, False, str(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check, rows))
    print(
        "TV entries:",
        len(results),
        "with posters:",
        sum(r[1] for r in results),
        "with synopses:",
        sum(r[2] for r in results),
        flush=True,
    )
    for title, _, _, error in results:
        if error:
            print("Metadata error:", title, error, flush=True)
    example = next(i for i in rows if i["type"] == "episode")
    overview = app.show_overview(example, state["settings"])
    print(
        "Full show:",
        overview["details"]["title"],
        "seasons:",
        len(overview["seasons"]),
        "Plex episodes:",
        overview["available"],
        "missing aired episodes:",
        overview["missing"],
        flush=True,
    )
