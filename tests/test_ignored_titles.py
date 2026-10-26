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
import ignored_titles as ignored


class IgnoredTitleTests(unittest.TestCase):
    def test_global_identity_and_show_scope(self):
        state = {}
        ignored.add(
            state, {"type": "movie", "tmdb": "10", "imdb": "tt10", "title": "Movie"}
        )
        self.assertTrue(
            ignored.matches(
                {"type": "movie", "imdb": "tt10", "title": "Other name"},
                state["ignored_titles"],
            )
        )
        self.assertFalse(
            ignored.matches({"type": "show", "tmdb": "10"}, state["ignored_titles"])
        )
        ignored.add(state, {"type": "show", "tmdb": "20", "title": "Series"})
        self.assertTrue(
            ignored.matches(
                {"type": "episode", "show_tmdb": "20", "season": 1, "episode": 2},
                state["ignored_titles"],
            )
        )
        isolated = {}
        ignored.add(
            isolated,
            {
                "type": "episode",
                "show_tmdb": "20",
                "season": 1,
                "episode": 2,
                "title": "Episode",
            },
        )
        self.assertTrue(
            ignored.matches(
                {"type": "episode", "show_tmdb": "20", "season": 1, "episode": 2},
                isolated["ignored_titles"],
            )
        )
        self.assertFalse(
            ignored.matches(
                {"type": "episode", "show_tmdb": "20", "season": 1, "episode": 3},
                isolated["ignored_titles"],
            )
        )

    def test_persists_and_restores_without_modifying_lists(self):
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch.object(app, "DATA", Path(folder)),
        ):
            original = [
                {
                    "id": "list",
                    "items": [{"type": "movie", "tmdb": "10", "title": "Movie"}],
                }
            ]
            app.save_state({"settings": {}, "lists": original})
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def post(action, body):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/ignore/" + action,
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    return json.load(response)

            try:
                saved = post("add", {"item": original[0]["items"][0]})
                self.assertEqual(len(app.read_state()["ignored_titles"]), 1)
                self.assertEqual(app.read_state()["lists"], original)
                post("add", {"item": original[0]["items"][0]})
                self.assertEqual(len(app.read_state()["ignored_titles"]), 1)
                self.assertEqual(
                    post("remove", {"id": saved["ignored_titles"][0]["id"]})[
                        "ignored_titles"
                    ],
                    [],
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_explore_fetches_beyond_ignored_results(self):
        state = {"settings": {"tmdb": {"key": "test"}}, "lists": []}
        ignored.add(state, {"type": "movie", "tmdb": "1", "title": "Ignored"})
        calls = []

        def tmdb(path, settings):
            calls.append(path)
            if path.startswith("genre/"):
                return {"genres": []}
            if path.startswith("discover/"):
                second = "page=2" in path
                return {
                    "results": [
                        {
                            "id": 2 if second else 1,
                            "title": "New" if second else "Ignored",
                            "vote_average": 8,
                            "vote_count": 500,
                        }
                    ],
                    "total_pages": 2,
                }
            return {}

        with patch("providers.cached_tmdb", side_effect=tmdb):
            result = explore.home(state, {"type": "movie"}, lambda settings: [])
        picks = [item for row in result["rows"] for item in row["items"]]
        self.assertTrue(any("page=2" in path for path in calls))
        self.assertEqual([r["tmdb"] for r in picks], ["2"])
