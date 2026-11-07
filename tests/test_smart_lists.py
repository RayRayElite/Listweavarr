# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
import app
import smart_lists
import list_sharing


class SmartListTests(unittest.TestCase):
    def state(self):
        items = [
            {
                "id": "a",
                "type": "movie",
                "title": "Ready",
                "tmdb": "1",
                "status": "available",
                "plex_keys": ["10"],
            },
            {
                "id": "b",
                "type": "movie",
                "title": "Watched",
                "tmdb": "2",
                "status": "available",
                "plex_keys": ["20"],
            },
            {
                "id": "c",
                "type": "episode",
                "title": "Unknown",
                "show_tmdb": "3",
                "season": 1,
                "episode": 1,
                "status": "available",
                "plex_keys": ["30"],
            },
            {
                "id": "d",
                "type": "movie",
                "title": "Future",
                "tmdb": "4",
                "status": "upcoming",
            },
            {
                "id": "e",
                "type": "show",
                "title": "Whole show",
                "tmdb": "5",
                "status": "available",
                "plex_keys": ["50"],
            },
        ]
        return {
            "settings": {"plex": {"url": "http://fixture", "key": "fixture"}},
            "lists": [
                {
                    "id": "source",
                    "name": "Source",
                    "updated_at": 100,
                    "compared_at": 100,
                    "items": items,
                    "watch_progress": {
                        "server": "http://fixture",
                        "checked_at": 200,
                        "items": [
                            {"id": "a", "state": "unwatched", "complete": False},
                            {"id": "b", "state": "watched", "complete": True},
                        ],
                    },
                }
            ],
        }

    def test_preview_exclusions_are_conservative_and_read_only(self):
        state = self.state()
        before = copy.deepcopy(state)
        result = smart_lists.preview(state, {"sources": ["source"]})
        self.assertEqual([row["title"] for row in result["items"]], ["Ready"])
        self.assertEqual(result["skipped"]["unknown"], 1)
        self.assertEqual(result["skipped"]["scope"], 1)
        self.assertEqual(state, before)
        include = smart_lists.preview(
            state, {"sources": ["source"], "include_unknown": True}
        )
        self.assertEqual(
            [row["title"] for row in include["items"]], ["Ready", "Unknown"]
        )
        state["lists"][0]["watch_progress"]["server"] = "http://other"
        self.assertEqual(
            smart_lists.preview(state, {"sources": ["source"]})["items"], []
        )

    def test_create_requires_review_and_never_reuses_stale_keys(self):
        state = self.state()
        body = {"sources": ["source"]}
        result = smart_lists.preview(state, body)
        with self.assertRaises(ValueError):
            smart_lists.create(state, dict(body, token=result["token"]), app.normalize)
        entry = smart_lists.create(
            state, dict(body, token=result["token"], confirmed=True), app.normalize
        )
        self.assertEqual(entry["items"][0]["status"], "unchecked")
        self.assertNotIn("plex_keys", entry["items"][0])
        self.assertNotIn("smart_snapshot", list_sharing.export(entry)["list"])
        again = smart_lists.create(
            state, dict(body, token=result["token"], confirmed=True), app.normalize
        )
        self.assertEqual(again["name"], "Ready from my lists (2)")
        state["settings"]["plex"]["key"] = "changed-account"
        with self.assertRaises(ValueError):
            smart_lists.create(
                state, dict(body, token=result["token"], confirmed=True), app.normalize
            )

    def test_stale_sources_ignored_titles_and_exact_duplicates(self):
        state = self.state()
        body = {"sources": ["source"]}
        result = smart_lists.preview(state, body)
        state["lists"][0]["items"][0]["status"] = "missing"
        with self.assertRaises(ValueError):
            smart_lists.create(
                state, dict(body, token=result["token"], confirmed=True), app.normalize
            )
        state = self.state()
        other = copy.deepcopy(state["lists"][0])
        other["id"] = "second"
        state["lists"].append(other)
        result = smart_lists.preview(state, {"sources": ["source", "second"]})
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["skipped"]["duplicate"], 1)


class PersonalRecipesTests(unittest.TestCase):
    def state(self):
        return {
            "settings": {"plex": {"url": "http://fixture", "key": "fixture"}},
            "lists": [
                {
                    "id": "source",
                    "name": "Followed shows",
                    "items": [
                        {
                            "id": "show",
                            "type": "show",
                            "title": "Returning show",
                            "tmdb": "10",
                        }
                    ],
                }
            ],
        }

    def test_comfort_personal_history_filters_and_review(self):
        from unittest.mock import patch

        state = self.state()
        catalog = [
            {
                "type": "movie",
                "title": "Loved",
                "ids": {"tmdb": "1"},
                "watched": True,
                "user_rating": 9,
                "view_count": 1,
            },
            {
                "type": "movie",
                "title": "Replay",
                "ids": {"tmdb": "2"},
                "watched": True,
                "view_count": 3,
            },
            {
                "type": "movie",
                "title": "Disliked",
                "ids": {"tmdb": "3"},
                "watched": True,
                "user_rating": 3,
                "view_count": 8,
            },
            {
                "type": "show",
                "title": "Many episodes",
                "ids": {"tmdb": "4"},
                "watched": True,
                "view_count": 0,
                "viewed_leaf_count": 1000,
            },
        ]
        body = {"kind": "comfort", "sources": [], "limit": 50}
        with patch("providers.peek_tmdb", return_value={}):
            result = smart_lists.personal_preview(state, body, catalog)
        self.assertEqual([row["title"] for row in result["items"]], ["Loved", "Replay"])
        created = smart_lists.create(
            state, dict(body, token=result["token"], confirmed=True), app.normalize
        )
        self.assertEqual(created["name"], "Comfort rotation")
        self.assertEqual(len(created["items"]), 2)
        self.assertTrue(all(row["status"] == "unchecked" for row in created["items"]))
        state["settings"]["plex"]["key"] = "other-profile"
        with self.assertRaises(ValueError):
            smart_lists.create(
                state, dict(body, token=result["token"], confirmed=True), app.normalize
            )

    def test_catchup_known_season_return_reads_unwatched_owned_episodes(self):
        import datetime
        from unittest.mock import patch

        state = self.state()
        today = datetime.date(2026, 11, 6)
        data = {
            "name": "Returning show",
            "status": "Returning Series",
            "next_episode_to_air": {
                "air_date": "2026-12-01",
                "season_number": 3,
                "episode_number": 1,
            },
            "last_episode_to_air": {"season_number": 2},
        }
        catalog = [{"type": "show", "key": "100", "ids": {"tmdb": "10"}}]
        episodes = [
            {"season": "0", "episode": "1", "watched": False},
            {"season": "1", "episode": "1", "title": "Watched", "watched": True},
            {"season": "2", "episode": "1", "title": "Catch me", "watched": False},
            {"season": "3", "episode": "1", "watched": False},
        ]
        body = {"kind": "catchup", "sources": ["source"], "limit": 50}
        with patch("providers.peek_tmdb", return_value=data):
            result = smart_lists.personal_preview(
                state, body, catalog, lambda key: episodes, today
            )
            self.assertEqual([row["title"] for row in result["items"]], ["Catch me"])
            self.assertIn("2026-12-01", result["items"][0]["reason"])
            self.assertEqual(result["skipped"]["watched"], 1)
            data["status"] = "Canceled"
            self.assertEqual(
                smart_lists.personal_preview(
                    state, body, catalog, lambda key: episodes, today
                )["items"],
                [],
            )
            data["status"] = "Returning Series"
            data["next_episode_to_air"]["season_number"] = 2
            data["next_episode_to_air"]["episode_number"] = 8
            self.assertEqual(
                smart_lists.personal_preview(
                    state, body, catalog, lambda key: episodes, today
                )["items"],
                [],
            )
