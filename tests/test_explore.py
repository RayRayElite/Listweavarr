# SPDX-License-Identifier: AGPL-3.0-only
import datetime
import unittest
from unittest.mock import patch

import explore


class ExploreTests(unittest.TestCase):
    def test_quality_floors_and_early_rating_thresholds(self):
        self.assertFalse(
            explore.qualifies({"type": "movie", "rating": 5.9, "vote_count": 5000})
        )
        self.assertFalse(
            explore.qualifies({"type": "movie", "rating": 9, "vote_count": 5})
        )
        self.assertTrue(
            explore.qualifies(
                {"type": "movie", "rating": 6.8, "vote_count": 40}, recent=True
            )
        )
        self.assertFalse(
            explore.qualifies(
                {"type": "movie", "rating": 6.8, "vote_count": 400}, quality="7.0"
            )
        )

    def test_selectable_rating_thresholds(self):
        for minimum in ("5.0", "6.0", "7.0", "8.0", "9.0"):
            with self.subTest(minimum=minimum):
                row = {"type": "movie", "rating": float(minimum), "vote_count": 500}
                self.assertTrue(explore.qualifies(row, quality=minimum))
                row["rating"] -= 0.1
                self.assertFalse(explore.qualifies(row, quality=minimum))

    def test_ownership_keeps_movie_and_show_ids_separate_and_falls_back_conservatively(
        self,
    ):
        owned = explore.ownership(
            [
                {
                    "type": "movie",
                    "title": "Owned",
                    "year": "2020",
                    "ids": {"tmdb": "7"},
                },
                {
                    "type": "show",
                    "title": "A Series",
                    "year": "2021",
                    "ids": {"tvdb": "8"},
                },
            ]
        )
        self.assertTrue(owned({"type": "movie", "tmdb": "7", "title": "Owned"}))
        self.assertFalse(owned({"type": "show", "tmdb": "7", "title": "Other"}))
        self.assertTrue(
            owned({"type": "show", "tmdb": "90", "title": "A Series", "year": "2021"})
        )

    def test_watched_genres_weight_more_than_collected(self):
        catalog = [
            {
                "key": "1",
                "type": "movie",
                "title": "Watched",
                "genres": ["Horror"],
                "watched": True,
                "ids": {"tmdb": "1"},
            },
            {
                "key": "2",
                "type": "movie",
                "title": "Collected",
                "genres": ["Comedy"],
                "watched": False,
                "ids": {"tmdb": "2"},
            },
        ]
        weights, seeds = explore.profile(catalog)
        self.assertGreater(weights["Horror"], weights["Comedy"])
        self.assertEqual(seeds[0]["title"], "Watched")

    def test_home_excludes_owned_low_rated_and_duplicate_titles(self):
        today = str(datetime.datetime.now(datetime.timezone.utc).date())
        catalog = [
            {
                "key": "1",
                "type": "movie",
                "title": "Owned",
                "year": today[:4],
                "ids": {"tmdb": "7"},
                "genres": ["Drama"],
            }
        ]
        rows = [
            {
                "id": 7,
                "title": "Owned",
                "vote_average": 8,
                "vote_count": 500,
                "release_date": today,
            },
            {
                "id": 8,
                "title": "Good discovery",
                "vote_average": 7.8,
                "vote_count": 500,
                "release_date": today,
            },
            {
                "id": 9,
                "title": "Low rated",
                "vote_average": 4,
                "vote_count": 500,
                "release_date": today,
            },
        ]

        def tmdb(path, settings):
            if path == "movie/7":
                return {"title": "Owned", "genres": [{"id": 18, "name": "Drama"}]}
            if path.startswith("genre/"):
                return {"genres": [{"id": 18, "name": "Drama"}]}
            if path.startswith("discover/"):
                return {"results": rows}
            return {}

        with (
            patch.object(explore, "library", return_value=(catalog, True)),
            patch("providers.cached_tmdb", side_effect=tmdb),
            patch("suggestions.discover", return_value={"items": []}),
        ):
            result = explore.home(
                {"settings": {"tmdb": {"key": "test"}}, "lists": []},
                {"type": "movie"},
                lambda s: catalog,
            )
        picks = [r for shelf in result["rows"] for r in shelf["items"]]
        self.assertEqual([r["title"] for r in picks], ["Good discovery"])
        self.assertTrue(result["library_connected"])

    def test_bad_good_is_opt_in(self):
        calls = []

        def tmdb(path, settings):
            calls.append(path)
            return {
                "genres": [],
                "results": [],
                "movie_results": [
                    {
                        "id": 9,
                        "title": "Cult film",
                        "vote_average": 3,
                        "vote_count": 500,
                    }
                ],
            }

        with (
            patch("providers.cached_tmdb", side_effect=tmdb),
            patch(
                "cult_discovery.candidates",
                return_value=(
                    [
                        {
                            "details": {
                                "id": 9,
                                "title": "Cult film",
                                "vote_average": 3,
                                "vote_count": 500,
                            },
                            "reasons": ["Cult and camp metadata"],
                            "confidence": "Experimental",
                        }
                    ],
                    [],
                ),
            ),
        ):
            plain = explore.home(
                {"settings": {"tmdb": {"key": "test"}}, "lists": []},
                {"type": "movie"},
                lambda s: [],
            )
            self.assertFalse(any(p.startswith("find/") for p in calls))
            cult = explore.home(
                {"settings": {"tmdb": {"key": "test"}}, "lists": []},
                {"type": "movie", "guilty": True},
                lambda s: [],
            )
        self.assertFalse(any(r["id"] == "cult" for r in plain["rows"]))
        self.assertEqual(
            next(r for r in cult["rows"] if r["id"] == "cult")["items"][0]["rating"], 3
        )

    def test_list_sources_are_honestly_labeled(self):
        state = {
            "settings": {},
            "lists": [
                {
                    "id": "saved",
                    "name": "Halloween",
                    "source": "https://letterboxd.com/user/list/halloween/",
                    "items": [{"status": "missing"}],
                }
            ],
        }
        result = explore.lists(state, {"source": "saved", "query": "Halloween"})
        self.assertEqual(result["lists"][0]["provider"], "Letterboxd")
        self.assertEqual(result["lists"][0]["missing"], 1)
        self.assertEqual(result["lists"][0]["saved_id"], "saved")

    def test_collection_preserves_release_order(self):
        with patch(
            "providers.cached_tmdb",
            return_value={
                "name": "Collection",
                "parts": [
                    {"id": 2, "title": "Later", "release_date": "2020-01-01"},
                    {"id": 1, "title": "Earlier", "release_date": "2010-01-01"},
                ],
            },
        ):
            result = explore.collection("3", {})
        self.assertEqual([r["tmdb"] for r in result["items"]], ["1", "2"])

    def test_home_excludes_tracked_titles_from_expanded_upcoming_shelf(self):
        future = str(
            datetime.datetime.now(datetime.timezone.utc).date()
            + datetime.timedelta(days=20)
        )

        def tmdb(path, settings):
            if path.startswith("discover/") or path.startswith("trending/"):
                return {
                    "total_pages": 1,
                    "results": [
                        {
                            "id": 42,
                            "title": "Tracked",
                            "media_type": "movie",
                            "release_date": future,
                            "original_language": "en",
                        }
                    ],
                }
            return {"genres": []}

        state = {
            "settings": {"tmdb": {"key": "test"}},
            "lists": [],
            "release_watchlist": [{"type": "movie", "tmdb": "42", "region": "CA"}],
        }
        with (
            patch.object(explore, "library", return_value=([], True)),
            patch("providers.cached_tmdb", side_effect=tmdb),
        ):
            result = explore.home(
                state, {"type": "movie", "shelf": "upcoming-movie"}, lambda s: []
            )
        self.assertFalse([row for shelf in result["rows"] for row in shelf["items"]])
