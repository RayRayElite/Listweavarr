# SPDX-License-Identifier: AGPL-3.0-only
"""Save/refresh the user's Marvel Trakt list and compare with Plex. No media/playlist writes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collections
import time
from verify_live import get, post

if __name__ == "__main__":
    url = "https://trakt.tv/users/rayrayelite/lists/marvel-universe-timeline-copy"
    state = get("/api/state")
    existing = next(
        (
            entry
            for entry in state["lists"]
            if (entry.get("source") or "").rstrip("/") == url
        ),
        None,
    )
    body = {"list_id": existing["id"]} if existing else {"url": url}
    job_id = post("import/start", body, state["csrf"])["job_id"]
    message = ""
    while True:
        job = get("/api/job?id=" + job_id)
        if job["message"] != message:
            message = job["message"]
            print(message, flush=True)
        if job["status"] == "error":
            raise RuntimeError(job["message"])
        if job["status"] == "complete":
            entry = job["result"]
            break
        time.sleep(1)
    result = post("compare", {"list_id": entry["id"]}, state["csrf"])
    print(
        "SAVED:",
        result["name"],
        "| entries:",
        len(result["items"]),
        "| statuses:",
        dict(collections.Counter(i["status"] for i in result["items"])),
        flush=True,
    )
    print("No Radarr/Sonarr requests or Plex playlist writes submitted.", flush=True)
