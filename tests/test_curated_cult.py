# SPDX-License-Identifier: AGPL-3.0-only
"""Curated membership constrains discovery while personal signals rank its picks."""
import unittest
from unittest.mock import patch
import cult_discovery


class CuratedCultTests(unittest.TestCase):
    def state(self, count=2):
        return {
            "settings": {"tmdb": {"key": "test"}},
            "lists": [
                {
                    "id": "curated",
                    "name": "So Bad Its Good",
                    "items": [
                        {"type": "movie", "tmdb": str(i), "title": "Title " + str(i)}
                        for i in range(10, 10 + count)
                    ],
                }
            ],
        }

    def metadata(self, path, settings):
        identifier = int(path.split("/")[1].split("?")[0])
        return {
            "id": identifier,
            "title": "Title " + str(identifier),
            "genres": [{"id": 1, "name": "Comedy"}] if identifier in (1, 11) else [],
            "credits": {"cast": [{"id": 99}] if identifier in (1, 11) else []},
            "keywords": {"keywords": []},
            "vote_average": 2,
            "vote_count": 10,
        }

    def test_watched_affinity_ranks_only_curated_titles(self):
        history = [
            {
                "type": "movie",
                "title": "Watched favorite",
                "ids": {"tmdb": "1"},
                "watched": True,
                "user_rating": 9,
            }
        ]
        with patch("providers.cached_tmdb", side_effect=self.metadata), patch(
            "cult_discovery.candidates",
            side_effect=AssertionError("No heuristic fallback"),
        ):
            found, _, more = cult_discovery.curated_candidates(self.state(), history)
        self.assertEqual({value["details"]["id"] for value in found}, {10, 11})
        self.assertEqual(found[0]["details"]["id"], 11)
        self.assertIn("Watched favorite", " ".join(found[0]["reasons"]))
        self.assertFalse(more)

    def test_ownership_alone_is_not_a_positive_signal(self):
        history = [
            {
                "type": "movie",
                "title": "Unwatched",
                "ids": {"tmdb": "1"},
                "watched": False,
            }
        ]
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            found, _, _ = cult_discovery.curated_candidates(self.state(), history)
        self.assertTrue(all(value["score"] == 0 for value in found))

    def test_explicit_dislike_and_ownership_filter_stay_effective(self):
        state = self.state()
        state["taste_feedback"] = {
            "movie:11": {
                "type": "movie",
                "tmdb": "11",
                "title": "Disliked",
                "value": "dislike",
                "genre_ids": [],
                "people": [],
            }
        }
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            found, _, _ = cult_discovery.curated_candidates(
                state, [], skip=lambda row: row.get("tmdb") == "10"
            )
        self.assertEqual(found, [])

    def test_missing_source_does_not_fall_back_and_pagination_is_disjoint(self):
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            empty, notices, more = cult_discovery.curated_candidates(
                {"settings": {}, "lists": []}, []
            )
            first, _, more_first = cult_discovery.curated_candidates(self.state(65), [])
            second, _, more_second = cult_discovery.curated_candidates(
                self.state(65), [], 2
            )
        self.assertEqual(empty, [])
        self.assertTrue(notices)
        self.assertFalse(more)
        self.assertEqual(len(first), 60)
        self.assertEqual(len(second), 5)
        self.assertTrue(more_first)
        self.assertFalse(more_second)
        self.assertFalse(
            {v["details"]["id"] for v in first} & {v["details"]["id"] for v in second}
        )
