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


class LanguagePreferenceTests(unittest.TestCase):
    def test_language_validation(self):
        self.assertEqual(explore.language_preferences(["en", "fr", "en"]), ["en", "fr"])
        for value in ("en", ["English"], ["en|fr"], [None]):
            with self.assertRaises(ValueError):
                explore.language_preferences(value)

    def test_explore_filters_all_shelves_and_queries_each_language(self):
        calls = []

        def tmdb(path, settings):
            calls.append(path)
            if path.startswith("genre/"):
                return {"genres": []}
            if path.startswith("discover/"):
                return {
                    "results": [
                        {
                            "id": 1,
                            "title": "English",
                            "original_language": "en",
                            "vote_average": 8,
                            "vote_count": 500,
                        },
                        {
                            "id": 2,
                            "title": "French",
                            "original_language": "fr",
                            "vote_average": 9,
                            "vote_count": 500,
                        },
                        {
                            "id": 3,
                            "title": "Unknown",
                            "vote_average": 8,
                            "vote_count": 500,
                        },
                    ]
                }
            return {}

        state = {
            "settings": {"tmdb": {"key": "test"}},
            "lists": [],
            "explore_languages": ["en"],
        }
        with patch("providers.cached_tmdb", side_effect=tmdb):
            english = explore.home(state, {"type": "movie"}, lambda settings: [])
            state["explore_languages"] = ["en", "fr"]
            both = explore.home(state, {"type": "movie"}, lambda settings: [])
            state["explore_languages"] = []
            all_languages = explore.home(state, {"type": "movie"}, lambda settings: [])
        titles = lambda result: [
            r["title"] for shelf in result["rows"] for r in shelf["items"]
        ]
        self.assertEqual(titles(english), ["English"])
        self.assertEqual(titles(both), ["English", "French"])
        self.assertEqual(titles(all_languages), ["English", "French", "Unknown"])
        self.assertTrue(any("with_original_language=en" in path for path in calls))
        self.assertTrue(any("with_original_language=fr" in path for path in calls))

    def test_preferences_persist_and_are_public_without_changing_lists(self):
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch.object(app, "DATA", Path(folder)),
        ):
            app.save_state({"settings": {}, "lists": []})
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/explore/preferences",
                    data=json.dumps({"languages": ["en", "fr"]}).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response)["languages"], ["en", "fr"])
                state = app.read_state()
                self.assertEqual(
                    app.public_state(state)["explore_languages"], ["en", "fr"]
                )
                self.assertEqual(state["lists"], [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
