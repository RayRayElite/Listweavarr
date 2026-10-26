# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise a clean CI container only; do not point this at a personal server."""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8765"
NAME = "Container persistence smoke test"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=3) as response:
        return json.load(response)


def wait():
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            assert get("/healthz")["application"] == "Listweavarr"
            return
        except (OSError, AssertionError):
            time.sleep(0.5)
    raise RuntimeError("Container did not become healthy")


def main():
    wait()
    state = get("/api/state")
    if sys.argv[-1] == "seed":
        assert not state["lists"], "Smoke checks require a clean disposable container"
        headers = {
            "Content-Type": "application/json",
            "X-Listweavarr-Token": state["csrf"],
        }
        req = urllib.request.Request(
            BASE + "/api/lists/edit",
            data=json.dumps({"name": NAME, "items": []}).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req) as response:
            assert json.load(response)["entry"]["name"] == NAME
        bad = urllib.request.Request(
            BASE + "/api/state", headers={"Host": "attacker.invalid"}
        )
        try:
            urllib.request.urlopen(bad)
            raise AssertionError("Unlisted Host accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        with urllib.request.urlopen(BASE + "/") as response:
            html = response.read().decode()
            assert "Listweavarr" in html and "reelcheck</span>" not in html
    else:
        assert any(
            row["name"] == NAME for row in state["lists"]
        ), "Configuration volume did not survive restart"
    print("Container", sys.argv[-1], "check passed")


if __name__ == "__main__":
    main()
