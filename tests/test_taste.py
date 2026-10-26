# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import app
import backups
import explore
import taste


class TasteTests(unittest.TestCase):
    def feedback(self, value="like", kind="movie"):
        return taste.record(
            kind,
            "1",
            value,
            {
                "title": "Favorite title",
                "genres": [{"id": 18, "name": "Drama"}],
                "credits": {"cast": [{"id": 9}]},
            },
        )

    def test_ownership_does_not_count_as_positive_taste(self):
        rows = [
            {
                "key": "a",
                "type": "movie",
                "title": "Owned",
                "ids": {"tmdb": "1"},
                "genres": ["Drama"],
                "watched": False,
            }
        ]
        weights, seeds = explore.profile(rows)
        self.assertEqual(dict(weights), {})
        self.assertEqual(seeds, [])

    def test_explicit_feedback_creates_seed_without_claiming_ownership(self):
        feedback = {"movie:1": self.feedback("favorite")}
        rows = taste.catalog_with_feedback([], feedback)
        weights, seeds = explore.profile(rows)
        self.assertEqual(seeds[0]["_feedback"], "favorite")
        self.assertEqual(weights["Drama"], 6)
        self.assertFalse(
            explore.ownership([])(
                {"type": "movie", "tmdb": "1", "title": "Favorite title"}
            )
        )

    def test_feedback_overrides_low_rating_and_dislikes_override_watches(self):
        row = {
            "key": "a",
            "type": "movie",
            "title": "Owned",
            "ids": {"tmdb": "1"},
            "genres": ["Drama"],
            "watched": True,
            "user_rating": 2,
        }
        _, seeds = explore.profile(
            taste.catalog_with_feedback([row], {"movie:1": self.feedback("like")})
        )
        self.assertEqual(len(seeds), 1)
        weights, seeds = explore.profile(
            taste.catalog_with_feedback([row], {"movie:1": self.feedback("dislike")})
        )
        self.assertEqual(seeds, [])
        self.assertEqual(dict(weights), {})
        self.assertNotIn("_feedback", row)

    def test_ranking_explanations_and_dislikes(self):
        candidates = [
            {
                "type": "movie",
                "tmdb": "2",
                "title": "Similar",
                "genre_ids": [18],
                "people_ids": ["9"],
                "score": 10,
                "reasons": ["Shared themes"],
            },
            {
                "type": "movie",
                "tmdb": "3",
                "title": "Other",
                "genre_ids": [35],
                "score": 10,
                "reasons": ["Popular"],
            },
        ]
        original = copy.deepcopy(candidates)
        result = taste.rank(candidates, {"movie:1": self.feedback("favorite")})
        self.assertEqual(result[0]["title"], "Similar")
        self.assertIn("favorited", result[0]["reasons"][0])
        self.assertEqual(candidates, original)
        negative = taste.rank(candidates, {"movie:1": self.feedback("dislike")})
        self.assertEqual(negative[0]["title"], "Other")

    def test_movie_and_tv_genre_ids_are_not_mixed(self):
        score, reasons = taste.affinity(
            {"type": "show", "tmdb": "2", "genre_ids": [18]},
            {"movie:1": self.feedback()},
        )
        self.assertEqual(score, 0)
        self.assertEqual(reasons, [])

    def test_direct_dislike_is_excluded_only_from_personal_ranking(self):
        rows = [{"type": "movie", "tmdb": "1", "title": "No", "score": 10}]
        self.assertEqual(taste.rank(rows, {"movie:1": self.feedback("dislike")}), [])
        self.assertEqual(len(rows), 1)

    def test_feedback_backup_and_validation(self):
        state = {"lists": [], "taste_feedback": {"movie:1": self.feedback()}}
        document = backups.export(state)
        restored, _ = backups.validate(document, app.normalize)
        self.assertEqual(restored["taste_feedback"], state["taste_feedback"])
        with self.assertRaises(ValueError):
            taste.validate({"bad": self.feedback()})


class TasteHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(app, "DATA", Path(self.folder.name))
        self.data_patch.start()
        app.save_state({"settings": {}, "lists": []})
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.data_patch.stop()
        self.folder.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(
            "http://127.0.0.1:" + str(self.server.server_port) + "/api/taste/" + path,
            data=json.dumps(body).encode(),
            headers={
                "Host": "127.0.0.1:8765",
                "X-Listweavarr-Token": app.SESSION,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_save_change_and_clear_feedback_uses_verified_metadata(self):
        with patch(
            "providers.cached_tmdb",
            return_value={
                "id": 1,
                "title": "Verified title",
                "genres": [{"id": 18, "name": "Drama"}],
            },
        ) as metadata:
            result = self.post(
                "set",
                {
                    "type": "movie",
                    "tmdb": "1",
                    "value": "like",
                    "title": "Untrusted title",
                },
            )
            self.assertEqual(result["items"]["movie:1"]["title"], "Verified title")
            self.post("set", {"type": "movie", "tmdb": "1", "value": "favorite"})
            self.assertEqual(
                self.post("list", {})["items"]["movie:1"]["value"], "favorite"
            )
        with patch("providers.cached_tmdb") as metadata:
            self.assertEqual(
                self.post("set", {"type": "movie", "tmdb": "1", "value": "clear"})[
                    "items"
                ],
                {},
            )
            metadata.assert_not_called()
        self.assertEqual(app.read_state()["lists"], [])

    def test_bad_feedback_does_not_write(self):
        for body in (
            {"type": "episode", "tmdb": "1", "value": "like"},
            {"type": "movie", "tmdb": "1", "value": "unknown"},
        ):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post("set", body)
            error.exception.close()
        self.assertEqual(self.post("list", {})["items"], {})
