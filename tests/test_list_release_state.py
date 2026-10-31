# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import app
import list_release_state as releases


class ListReleaseTests(unittest.TestCase):
    def test_metadata_outage_does_not_turn_known_upcoming_into_missing(self):
        item = {"type": "movie", "title": "Future", "tmdb": "1", "status": "upcoming"}
        with patch("app.plex_catalog", return_value=[]), patch(
            "providers.peek_tmdb", return_value={}
        ):
            self.assertEqual(app.compare([item], {"plex": {}})[0]["status"], "upcoming")
        with patch("app.plex_catalog", return_value=[]), patch(
            "providers.peek_tmdb", return_value={"release_date": "2000-01-01"}
        ):
            self.assertEqual(app.compare([item], {"plex": {}})[0]["status"], "missing")

    def test_owned_early_copy_stays_available(self):
        catalog = [
            {
                "key": "10",
                "type": "movie",
                "title": "Film",
                "library": "Movies",
                "ids": {"tmdb": "1"},
            }
        ]
        with patch("app.plex_catalog", return_value=catalog), patch(
            "list_release_state.classify"
        ) as release:
            result = app.compare(
                [{"type": "movie", "title": "Film", "tmdb": "1"}], {"plex": {}}
            )[0]
        self.assertEqual(result["status"], "available")
        release.assert_not_called()

    def test_future_movie_not_missing_or_requestable_as_released(self):
        with patch("app.plex_catalog", return_value=[]), patch(
            "providers.peek_tmdb", return_value={"release_date": "2999-01-01"}
        ):
            result = app.compare(
                [{"type": "movie", "title": "Future", "tmdb": "1"}], {"plex": {}}
            )[0]
        self.assertEqual(result["status"], "upcoming")
        self.assertIn("2999-01-01", result["detail"])

    def test_future_episode_uses_its_own_date_not_series_premiere(self):
        def peek(path):
            return (
                {"first_air_date": "2000-01-01"}
                if path == "tv/1"
                else {"episodes": [{"episode_number": 2, "air_date": "2999-01-01"}]}
            )

        with patch("providers.peek_tmdb", side_effect=peek):
            result = releases.upcoming(
                {"type": "episode", "show_tmdb": "1", "season": "3", "episode": "2"},
                {},
                {},
            )
        self.assertEqual(result["date"], "2999-01-01")

    def test_unknown_dates_are_not_invented_and_released_status_wins(self):
        for data in (
            {},
            {"release_date": "invalid"},
            {"release_date": "2000-01-01", "status": "Post Production"},
        ):
            with patch("providers.peek_tmdb", return_value=data), patch(
                "providers.cached_tmdb"
            ) as remote:
                self.assertIsNone(
                    releases.upcoming(
                        {"type": "movie", "tmdb": "1", "year": "2000"}, {}, {}
                    )
                )
                remote.assert_not_called()
        with patch("providers.peek_tmdb", return_value={"status": "Planned"}):
            self.assertIsNone(
                releases.upcoming({"type": "show", "tmdb": "1"}, {}, {})["date"]
            )
        with patch("providers.peek_tmdb", return_value={"status": "In Production"}):
            self.assertIn(
                "not announced",
                releases.upcoming({"type": "movie", "tmdb": "1"}, {}, {})["detail"],
            )

    def test_refresh_budget_and_scope_cache_bound_reads(self):
        cache = {}
        with patch("providers.peek_tmdb", return_value={}), patch(
            "providers.cached_tmdb", return_value={}
        ) as remote:
            for _ in range(2):
                for i in range(12):
                    releases.upcoming(
                        {"type": "movie", "tmdb": str(i + 1), "year": "2999"},
                        {"tmdb": {"key": "private"}},
                        cache,
                    )
        self.assertEqual(remote.call_count, 8)
