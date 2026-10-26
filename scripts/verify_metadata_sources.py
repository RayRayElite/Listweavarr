# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only provider checks. Never prints connection credentials."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import time
import app
import metadata_sources as metadata
import suggestions

settings = app.read_state()["settings"]
recommendations = suggestions.discover("movie", "1726", settings)
print("Broader suggestions:", len(recommendations["items"]), "candidates", flush=True)
for row in recommendations["items"][:5]:
    print(row["title"], row["type"], row["reasons"], flush=True)
for kind, identifier in [("movie", "1726"), ("show", "30991")]:
    started = time.time()
    result = metadata.enrich(kind, identifier, settings)
    print(kind, identifier, "elapsed", round(time.time() - started, 1), flush=True)
    for source in result["sources"]:
        print(
            source["provider"],
            source["status"],
            "facts",
            len(source.get("facts", [])),
            "sequence",
            len(source.get("sequence", [])),
            "franchise",
            len(source.get("franchise", [])),
            "connections",
            len(source.get("connections", [])),
            "notes",
            source.get("notes", [])[:2],
            flush=True,
        )
