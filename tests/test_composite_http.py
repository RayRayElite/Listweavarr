# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise reviewed generation through HTTP against a disposable workspace."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import app


class CompositeHTTPTests(unittest.TestCase):
    def test_preview_requires_unchanged_sources_and_explicit_creation(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.DATA", Path(folder)):
            sources = [
                {
                    "id": i,
                    "name": i,
                    "items": [{"id": i, "type": "movie", "title": i, "tmdb": str(n)}],
                }
                for n, i in enumerate(("one", "two"), 1)
            ]
            app.save_state({"settings": {}, "lists": sources}, backup=False)
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()

            def post(action, body):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/lists/{action}",
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    return json.load(response)

            try:
                body = {"sources": ["one", "two"], "operation": "union"}
                proposal = post("composite-preview", body)
                self.assertEqual(len(app.read_state()["lists"]), 2)
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    post(
                        "composite-create",
                        {**body, "fingerprint": proposal["fingerprint"]},
                    )
                failure.exception.close()
                changed = app.read_state()
                changed["lists"][0]["items"][0]["tmdb"] = "3"
                app.save_state(changed)
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    post(
                        "composite-create",
                        {
                            **body,
                            "name": "Combined",
                            "confirmed": True,
                            "fingerprint": proposal["fingerprint"],
                        },
                    )
                failure.exception.close()
                proposal = post("composite-preview", body)
                entry = post(
                    "composite-create",
                    {
                        **body,
                        "name": "Combined",
                        "confirmed": True,
                        "fingerprint": proposal["fingerprint"],
                    },
                )["entry"]
                self.assertEqual([r["tmdb"] for r in entry["items"]], ["3", "2"])
                self.assertEqual(app.read_state()["lists"][:2], changed["lists"])
                self.assertEqual(
                    entry["composite"]["recipe"]["sources"], ["one", "two"]
                )
            finally:
                server.shutdown()
                server.server_close()
