# SPDX-License-Identifier: AGPL-3.0-only
"""Boot the actual ZIP in isolation, restore a backup and restart its data.

Only synthetic data and an ephemeral local port are used. Never contacts Plex,
download managers or the private developer workspace. Suitable for CI and local
release review; a temporary installation is removed after the child exits.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(archive):
    with tempfile.TemporaryDirectory(prefix="listweavarr-release-") as folder:
        target = Path(folder)
        with zipfile.ZipFile(archive) as package:
            package.extractall(target)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(
            os.environ,
            LISTWEAVARR_DATA_DIR=str(target / "private-test-data"),
            LISTWEAVARR_HOST="127.0.0.1",
            LISTWEAVARR_PORT=str(port),
            LISTWEAVARR_PUBLIC_URL=base,
            LISTWEAVARR_OPEN_BROWSER="0",
            LISTWEAVARR_CURATOR_MODE="0",
            LISTWEAVARR_ALLOWED_HOSTS="",
        )

        def start():
            process = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=target,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Packaged server exited during startup")
                try:
                    with urllib.request.urlopen(
                        base + "/healthz", timeout=1
                    ) as response:
                        assert json.load(response)["application"] == "Listweavarr"
                    return process
                except OSError:
                    time.sleep(0.1)
            process.terminate()
            process.wait(timeout=10)
            raise RuntimeError("Packaged server did not become healthy")

        def stop(process):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        def get_state():
            with urllib.request.urlopen(base + "/api/state", timeout=5) as response:
                return json.load(response)

        def post(action, body):
            request = urllib.request.Request(
                base + "/api/" + action,
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Listweavarr-Token": get_state()["csrf"],
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)

        process = start()
        try:
            assert not get_state()["lists"]
            with urllib.request.urlopen(base + "/", timeout=5) as response:
                assert b"Listweavarr" in response.read()
            post(
                "lists/edit",
                {
                    "name": "Release recovery fixture",
                    "items": [
                        {"type": "movie", "title": "Synthetic movie", "tmdb": "1"}
                    ],
                },
            )
            backup = post("backup/export", {})
            assert "settings" not in backup["data"]
            preview = post("backup/preview", {"document": backup})
            post(
                "backup/restore",
                {
                    "document": backup,
                    "fingerprint": preview["fingerprint"],
                    "mode": "replace",
                },
            )
            assert get_state()["lists"][0]["name"] == "Release recovery fixture"
        finally:
            stop(process)
        process = start()
        try:
            restored = get_state()["lists"][0]
            assert restored["items"][0]["tmdb"] == "1"
            assert restored["items"][0]["status"] == "unchecked"
        finally:
            stop(process)
    print("Packaged clean startup, reviewed backup restore and data restart passed")


if __name__ == "__main__":
    version = (ROOT / "VERSION").read_text().strip()
    run(ROOT / "releases" / f"Listweavarr-{version}.zip")
