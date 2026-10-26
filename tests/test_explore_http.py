# SPDX-License-Identifier: AGPL-3.0-only
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app


class ExploreHTTPTests(unittest.TestCase):
    def test_save_is_local_compared_and_does_not_download(self):
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch.object(app, "DATA", Path(folder)),
        ):
            app.save_state(
                {
                    "settings": {
                        "plex": {"url": "http://example.test", "key": "saved"}
                    },
                    "lists": [],
                }
            )
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def post(path, body):
                req = urllib.request.Request(
                    "http://127.0.0.1:"
                    + str(server.server_port)
                    + "/api/explore/"
                    + path,
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(req) as response:
                    return json.load(response)

            try:
                with (
                    patch(
                        "providers.list_details",
                        return_value={
                            "title": "Provider title",
                            "release_date": "2020-01-01",
                        },
                    ),
                    patch.object(
                        app,
                        "compare",
                        side_effect=lambda rows, settings: [
                            dict(r, status="missing") for r in rows
                        ],
                    ),
                    patch.object(app, "request_item") as download,
                ):
                    result = post(
                        "save",
                        {
                            "items": [
                                {
                                    "type": "movie",
                                    "tmdb": "42",
                                    "title": "Untrusted title",
                                }
                            ]
                        },
                    )
                self.assertEqual(result["entry"]["items"][0]["title"], "Provider title")
                self.assertEqual(result["entry"]["items"][0]["status"], "missing")
                self.assertEqual(len(app.read_state()["lists"]), 1)
                download.assert_not_called()
                with patch.object(
                    app.explore,
                    "lists",
                    return_value={"lists": [], "page": 1, "has_more": False},
                ):
                    post("lists", {"query": "Marvel"})
                self.assertEqual(len(app.read_state()["lists"]), 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
