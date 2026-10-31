# SPDX-License-Identifier: AGPL-3.0-only
"""Compare coverage within Plex's configured order, never across providers."""
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import app


class ComparisonOrderTests(unittest.TestCase):
    def test_undated_next_season_does_not_hide_complete_aired_coverage(self):
        item = {"id": "series", "type": "show", "title": "Returning show", "tmdb": "1"}
        match = {
            "key": "10",
            "type": "show",
            "title": "Returning show",
            "library": "TV",
            "ids": {"tmdb": "1"},
        }

        def metadata(path, settings):
            if path == "tv/1":
                return {"seasons": [{"season_number": 1}, {"season_number": 2}]}
            season = int(path.rsplit("/", 1)[1])
            return {
                "episodes": [
                    {
                        "season_number": season,
                        "episode_number": e,
                        "air_date": "2000-01-01" if season == 1 else None,
                    }
                    for e in range(1, (6 if season == 1 else 8) + 1)
                ]
            }

        for count, status in [(6, "available"), (5, "partial")]:
            leaves = [
                {"key": str(i), "season": "1", "episode": str(i)}
                for i in range(1, count + 1)
            ]
            with patch("app.plex_catalog", return_value=[match]), patch(
                "app.plex_leaves", return_value=leaves
            ), patch("app.plex_episode_order", return_value="tmdbAiring"), patch(
                "providers.tmdb", side_effect=metadata
            ):
                result = app.compare([item], {"plex": {}, "tmdb": {"key": "private"}})[
                    0
                ]
            self.assertEqual(result["status"], status)
            self.assertIn(f"{count}/6", result["detail"])
            self.assertIn("8 undated", result["detail"])
            self.assertEqual(result["missing_episodes"], 6 - count)

    def test_sonarr_undated_rows_are_excluded_without_discarding_aired_rows(self):
        rows = [
            {"seasonNumber": 1, "episodeNumber": 1, "airDate": "2000-01-01"},
            {"seasonNumber": 2, "episodeNumber": 1, "airDate": None},
        ]
        with patch("app.plex_episode_order", return_value="tvdbAiring"), patch(
            "app.arr_call", side_effect=[[{"id": 3, "tvdbId": 2}], rows]
        ):
            expected, note = app.expected_episodes(
                {"type": "show", "tvdb": "2"},
                {"ids": {}},
                {"sonarr": {"key": "private"}},
                {},
            )
        self.assertEqual(expected, {("1", "1")})
        self.assertIn("1 undated", note)

    def test_no_confirmed_air_dates_do_not_override_owned_early_copies(self):
        match = {
            "key": "10",
            "type": "show",
            "title": "Show",
            "library": "TV",
            "ids": {"tmdb": "1"},
        }
        for leaves, status in [
            ([], "upcoming"),
            ([{"key": "20", "season": "1", "episode": "1"}], "available"),
        ]:
            with patch("app.plex_catalog", return_value=[match]), patch(
                "app.plex_leaves", return_value=leaves
            ), patch(
                "app.expected_episodes",
                return_value=(set(), "TMDB; undated episodes not counted yet"),
            ):
                result = app.compare(
                    [{"type": "show", "title": "Show", "tmdb": "1"}], {"plex": {}}
                )[0]
            self.assertEqual(result["status"], status)

    def settings(self):
        return {
            "plex": {"url": "http://plex", "key": "private"},
            "tmdb": {"key": "private"},
            "sonarr": {"key": "private"},
        }

    def test_inherited_tmdb_order_counts_all_79_and_real_missing_episode(self):
        match = {
            "key": "10",
            "library_id": "2",
            "type": "show",
            "title": "Fusion",
            "library": "TV",
            "ids": {"tmdb": "37851", "tvdb": "202241"},
        }
        item = {"id": "fusion", "title": "Fusion", "type": "show", "tmdb": "37851"}
        leaves = [
            {"season": str(s), "episode": str(e), "key": str(s * 100 + e)}
            for s, count in [(1, 54), (2, 25)]
            for e in range(1, count + 1)
        ]

        def tmdb(path, settings):
            if path == "tv/37851":
                return {"seasons": [{"season_number": 1}, {"season_number": 2}]}
            season = int(path.rsplit("/", 1)[1])
            return {
                "episodes": [
                    {
                        "season_number": season,
                        "episode_number": e,
                        "air_date": "2000-01-01",
                    }
                    for e in range(1, (54 if season == 1 else 25) + 1)
                ]
            }

        for present, expected_status, count in [
            (leaves, "available", 79),
            (leaves[:-1], "partial", 78),
        ]:
            with patch("app.plex_catalog", return_value=[match]), patch(
                "app.plex_leaves", return_value=present
            ), patch(
                "app.remote",
                side_effect=[
                    ET.fromstring(
                        '<MediaContainer><Directory><Preferences><Setting id="showOrdering" value=""/></Preferences></Directory></MediaContainer>'
                    ),
                    ET.fromstring(
                        '<MediaContainer><Setting id="showOrdering" value="tmdbAiring"/></MediaContainer>'
                    ),
                ],
            ), patch(
                "providers.tmdb", side_effect=tmdb
            ), patch(
                "app.arr_call"
            ) as sonarr:
                result = app.compare([item], self.settings())[0]
            self.assertEqual(result["status"], expected_status)
            self.assertIn(f"{count}/79", result["detail"])
            self.assertIn("TMDB", result["detail"])
            sonarr.assert_not_called()

    def test_show_override_wins_and_is_cached(self):
        cache = {}
        with patch(
            "app.remote",
            return_value=ET.fromstring(
                '<MediaContainer><Directory><Preferences><Setting id="showOrdering" value="tvdbAiring"/></Preferences></Directory></MediaContainer>'
            ),
        ) as remote:
            for _ in range(2):
                self.assertEqual(
                    app.plex_episode_order(
                        {"key": "10", "library_id": "2"}, self.settings(), cache
                    ),
                    "tvdbAiring",
                )
            self.assertEqual(remote.call_count, 1)

    def test_alternate_order_does_not_claim_missing_from_aired_coordinates(self):
        with patch("app.plex_episode_order", return_value="dvd"), patch(
            "app.arr_call"
        ) as sonarr, patch("providers.tmdb") as tmdb:
            expected, note = app.expected_episodes(
                {"type": "show"}, {"ids": {}}, self.settings(), {}
            )
        self.assertIsNone(expected)
        self.assertIn("alternate episode order", note)
        sonarr.assert_not_called()
        tmdb.assert_not_called()

    def test_missing_tmdb_does_not_fall_back_to_different_sonarr_order(self):
        with patch("app.plex_episode_order", return_value="tmdbAiring"), patch(
            "providers.tmdb", side_effect=ValueError("offline")
        ), patch("app.arr_call") as sonarr:
            expected, note = app.expected_episodes(
                {"type": "show", "tmdb": "1"}, {"ids": {}}, self.settings(), {}
            )
        self.assertIsNone(expected)
        self.assertIn("not substituted", note)
        sonarr.assert_not_called()
