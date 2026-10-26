# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
from unittest.mock import patch

import app
import text_list_builder


class TitleWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "settings": {"plex": {"key": "test-only", "url": "http://localhost:32400"}},
            "lists": [],
            "requests": [],
        }

    def test_exact_owned_movie_is_available_without_creating_a_list(self):
        catalog = [
            {
                "type": "movie",
                "key": "5",
                "title": "Film",
                "year": "2020",
                "ids": {"tmdb": "42"},
                "library": "Movies",
            }
        ]
        before = copy.deepcopy(self.state)
        with (
            patch.object(app.explore, "library", return_value=(catalog, True)),
            patch.object(app.providers, "peek_tmdb", return_value={}),
        ):
            result = app.title_workspace_state(
                {"type": "movie", "tmdb": "42"}, self.state
            )
        self.assertEqual(result["ownership"], "available")
        self.assertFalse(result["can_request"])
        self.assertEqual(self.state, before)

    def test_scope_does_not_inherit_parent_show_ownership(self):
        catalog = [
            {
                "type": "show",
                "key": "5",
                "title": "Series",
                "ids": {"tmdb": "42"},
                "library": "TV",
            }
        ]
        with (
            patch.object(app.explore, "library", return_value=(catalog, True)),
            patch.object(app.providers, "peek_tmdb", return_value={}),
            patch.object(
                app,
                "plex_leaves",
                return_value=[{"season": "1", "episode": "1", "key": "10"}],
            ),
        ):
            result = app.title_workspace_state(
                {"type": "episode", "tmdb": "42", "season": "1", "episode": "2"},
                self.state,
            )
        self.assertEqual(result["ownership"], "missing")
        self.assertTrue(result["can_request"])

    def test_existing_request_and_tracking_are_reported(self):
        self.state["requests"] = [
            {
                "id": "request-1",
                "item": {"type": "movie", "tmdb": "42", "title": "Film"},
                "status": "downloading",
                "updated_at": 1,
            }
        ]
        self.state["release_watchlist"] = [
            {"id": "watch-1", "type": "movie", "tmdb": "42", "region": "CA"}
        ]
        with (
            patch.object(app.explore, "library", return_value=([], True)),
            patch.object(
                app.providers, "peek_tmdb", return_value={"release_date": "2099-01-01"}
            ),
        ):
            result = app.title_workspace_state(
                {"type": "movie", "tmdb": "42"}, self.state
            )
        self.assertEqual(result["request"]["status"], "downloading")
        self.assertTrue(result["tracked"])
        self.assertTrue(result["upcoming"])

    def test_future_date_uses_title_details_cache_variant(self):
        def cached(path):
            return (
                {"release_date": "2099-01-01"}
                if path == "movie/42?append_to_response=videos,credits,external_ids"
                else {}
            )

        with (
            patch.object(app.explore, "library", return_value=([], True)),
            patch.object(app.providers, "peek_tmdb", side_effect=cached),
        ):
            result = app.title_workspace_state(
                {"type": "movie", "tmdb": "42"}, self.state
            )
        self.assertTrue(result["upcoming"])

    def test_named_pilot_preserves_full_parent_title(self):
        rows = text_list_builder.infer(
            'Star Trek: The Original Series pilot "The Cage"'
        )
        self.assertEqual(rows[0]["query"], "Star Trek: The Original Series")
        self.assertEqual(rows[0]["episode_title"], "The Cage")
        self.assertEqual(rows[0]["type"], "episode")
