# SPDX-License-Identifier: AGPL-3.0-only
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
import app
import explore


class SearchIssueApiTests(unittest.TestCase):
    def test_search_is_read_only_and_only_notebook_save_changes_state(self):
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            app.save_state(
                {
                    "settings": {
                        "plex": {"url": "http://search-fixture", "key": "fixture"},
                        "tmdb": {"key": "fixture"},
                    },
                    "lists": [
                        {
                            "id": "list",
                            "name": "Fixture order",
                            "items": [
                                {
                                    "id": "item",
                                    "type": "movie",
                                    "title": "Fixture title",
                                    "tmdb": "10",
                                    "status": "missing",
                                }
                            ],
                        }
                    ],
                }
            )
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()

            def post(path, body):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/" + path,
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    return json.load(response)

            try:
                explore._library_cache.clear()
                catalog = [
                    {
                        "type": "movie",
                        "title": "Fixture title",
                        "ids": {"tmdb": "10"},
                        "key": "1",
                        "library": "Movies",
                    }
                ]
                with patch("app.save_state", wraps=app.save_state) as save, patch(
                    "app.arr_call",
                    side_effect=AssertionError("These routes never request media"),
                ), patch("app.plex_catalog", return_value=catalog) as plex, patch(
                    "official_lists.catalogue", return_value={"lists": []}
                ), patch(
                    "providers.peek_tmdb", return_value={}
                ), patch(
                    "providers.cached_tmdb",
                    return_value={
                        "results": [
                            {"id": 10, "media_type": "movie", "title": "Fixture title"}
                        ],
                        "total_pages": 1,
                    },
                ) as provider:
                    local = post("search/local", {"query": "Fixture"})
                    self.assertFalse(local["library_known"])
                    plex.assert_not_called()
                    provider.assert_not_called()
                    save.assert_not_called()
                    self.assertEqual(post("search/index", {})["count"], 1)
                    local = post("search/local", {"query": "Fixture"})
                    self.assertTrue(local["titles"][0]["in_plex"])
                    post("search/provider", {"query": "Fixture"})
                    self.assertEqual(provider.call_count, 1)
                    save.assert_not_called()
                    saved = post(
                        "issues/save",
                        {
                            "list_id": "list",
                            "item_id": "item",
                            "note": "Wrong audio track",
                            "category": "audio",
                        },
                    )
                    notes = post("issues/list", {})
                    self.assertEqual(notes["items"][0]["id"], saved["id"])
                    self.assertEqual(save.call_count, 1)
                    self.assertEqual(
                        app.read_state()["lists"][0]["items"][0]["status"], "missing"
                    )
            finally:
                server.shutdown()
                server.server_close()
                explore._library_cache.clear()
