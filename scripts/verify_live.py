# SPDX-License-Identifier: AGPL-3.0-only
"""Import the user's public examples and compare with Plex. Never requests downloads."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collections
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
URLS = [
    "https://letterboxd.com/ben_vlbd/list/sony-spider-man-multiverse-spumc-ranking/",
    "https://letterboxd.com/mysteriis666/list/halloween/",
    "https://mdblist.com/lists/rip/marvel-cinematic-universe-mcu-in-universe-chronological-order",
]


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=300) as response:
        return json.load(response)


def post(path, body, csrf):
    request = urllib.request.Request(
        BASE + "/api/" + path,
        json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Listweavarr-Token": csrf},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


if __name__ == "__main__":
    state = get("/api/state")
    for url in URLS:
        existing = next(
            (
                l
                for l in state["lists"]
                if (l.get("source") or "").rstrip("/") == url.rstrip("/")
            ),
            None,
        )
        result = post(
            "import/start",
            {"list_id": existing["id"]} if existing else {"url": url},
            state["csrf"],
        )
        job_id, previous = result["job_id"], ""
        while True:
            job = get("/api/job?id=" + job_id)
            if job["message"] != previous:
                print(job["message"], flush=True)
                previous = job["message"]
            if job["status"] == "error":
                raise RuntimeError(job["message"])
            if job["status"] == "complete":
                entry = job["result"]
                break
            time.sleep(1)
        print("Comparing", entry["name"], flush=True)
        compared = post("compare", {"list_id": entry["id"]}, state["csrf"])
        print(
            "COMPARISON",
            dict(collections.Counter(i["status"] for i in compared["items"])),
            flush=True,
        )
