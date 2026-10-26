# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import suggestions


class SuggestionTests(unittest.TestCase):
    def test_matches_are_explained_and_movie_show_ids_stay_distinct(self):
        title = {
            "genres": [{"id": 1, "name": "Drama"}],
            "keywords": {"keywords": [{"id": 2, "name": "space"}]},
            "credits": {
                "cast": [{"id": 10, "name": "Actor"}],
                "crew": [{"id": 11, "name": "Director", "job": "Director"}],
            },
        }
        movie = {
            "id": 7,
            "title": "Film",
            "media_type": "movie",
            "genre_ids": [1],
            "vote_count": 500,
            "vote_average": 8,
        }
        show = {
            "id": 7,
            "name": "Show",
            "media_type": "tv",
            "genre_ids": [1],
            "vote_count": 500,
            "vote_average": 8,
        }

        def lookup(path, settings):
            if "append_to_response" in path:
                return title
            if path.startswith("person/10/"):
                return {"cast": [movie, show]}
            if path.startswith("person/11/"):
                return {
                    "crew": [dict(movie, job="Director"), dict(show, job="Producer")]
                }
            return {"results": [movie if "/movie?" in path else show]}

        with patch("providers.cached_tmdb", side_effect=lookup):
            result = suggestions.discover("movie", "1", {})
        self.assertEqual({r["key"] for r in result["items"]}, {"movie:7", "tv:7"})
        film = next(r for r in result["items"] if r["key"] == "movie:7")
        self.assertIn("Directed by Director", film["reasons"])
        series = next(r for r in result["items"] if r["key"] == "tv:7")
        self.assertNotIn("Directed by Director", series["reasons"])

    def test_current_title_and_adult_results_are_excluded(self):
        def lookup(path, settings):
            if "append_to_response" in path:
                return {"genres": [{"id": 1, "name": "Drama"}]}
            return {
                "results": [
                    {"id": 1, "title": "Current", "genre_ids": [1]},
                    {"id": 2, "title": "Adult", "adult": True, "genre_ids": [1]},
                ]
            }

        with patch("providers.cached_tmdb", side_effect=lookup):
            self.assertEqual(suggestions.discover("movie", "1", {})["items"], [])

    def test_invalid_id_never_fetches(self):
        with patch("providers.cached_tmdb") as lookup:
            with self.assertRaises(ValueError):
                suggestions.discover("movie", "../x", {})
        lookup.assert_not_called()

    def test_talk_show_and_self_appearances_do_not_dominate_cast_matches(self):
        def lookup(path, settings):
            if "append_to_response" in path:
                return {"credits": {"cast": [{"id": 10, "name": "Actor"}]}}
            return {
                "cast": [
                    {
                        "id": 1,
                        "name": "Talk show",
                        "media_type": "tv",
                        "genre_ids": [10767],
                    },
                    {
                        "id": 2,
                        "title": "Interview",
                        "media_type": "movie",
                        "character": "Self",
                    },
                    {
                        "id": 3,
                        "title": "Actual role",
                        "media_type": "movie",
                        "character": "Hero",
                    },
                ]
            }

        with patch("providers.cached_tmdb", side_effect=lookup):
            result = suggestions.discover("movie", "9", {})
        self.assertEqual([r["title"] for r in result["items"]], ["Actual role"])
