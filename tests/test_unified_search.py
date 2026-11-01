# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
from unittest.mock import patch
import unified_search as search
import explore


class UnifiedSearchTests(unittest.TestCase):
    def state(self):
        return {
            "settings": {},
            "lists": [
                {
                    "id": "one",
                    "name": "MCU order",
                    "description": "A chronological collection",
                    "items": [
                        {
                            "id": "m",
                            "type": "movie",
                            "title": "The Example",
                            "year": "2020",
                            "tmdb": "10",
                            "imdb": "tt0000010",
                        },
                        {
                            "id": "ep",
                            "type": "episode",
                            "title": "Pilot",
                            "show_title": "Example Show",
                            "show_tmdb": "20",
                            "season": "1",
                            "episode": "1",
                            "status": "available",
                        },
                    ],
                },
                {
                    "id": "two",
                    "name": "Another list",
                    "items": [
                        {
                            "id": "same",
                            "type": "movie",
                            "title": "The Example",
                            "tmdb": "10",
                        }
                    ],
                },
            ],
            "requests": [
                {
                    "id": "request",
                    "item": {"type": "movie", "title": "The Example", "tmdb": "10"},
                    "status": "downloading",
                    "updated_at": 10,
                }
            ],
        }

    def catalog(self):
        return [
            {
                "type": "movie",
                "title": "The Example",
                "year": "2020",
                "ids": {"tmdb": "10", "imdb": "tt0000010"},
                "key": "7",
                "server_id": "server",
                "library": "Movies",
            },
            {
                "type": "show",
                "title": "Example Show",
                "ids": {"tmdb": "20"},
                "key": "8",
                "server_id": "server",
                "library": "TV",
            },
        ]

    def test_local_is_read_only_exact_deduplicated_and_illustrated_without_network(
        self,
    ):
        state = self.state()
        before = copy.deepcopy(state)
        with patch(
            "providers.cached_tmdb",
            side_effect=AssertionError("Local search must not call providers"),
        ), patch("providers.peek_tmdb", return_value={"poster_path": "/poster.jpg"}):
            result = search.local(state, {"query": "example"}, self.catalog(), True)
        self.assertEqual(len(result["titles"]), 3)
        movie = next(r for r in result["titles"] if r["item"]["type"] == "movie")
        self.assertEqual(len(movie["lists"]), 2)
        self.assertTrue(movie["in_plex"])
        self.assertEqual(movie["request_status"], "downloading")
        self.assertTrue(movie["item"]["poster"].endswith("poster.jpg"))
        episode = next(r for r in result["titles"] if r["item"]["type"] == "episode")
        self.assertFalse(episode["in_plex"])
        self.assertTrue(episode["parent_in_plex"])
        self.assertEqual(state, before)

    def test_unknown_library_never_claims_missing_and_conflicts_do_not_merge(self):
        state = self.state()
        state["lists"][1]["items"][0]["imdb"] = "tt0000099"
        with patch("providers.peek_tmdb", return_value={}):
            result = search.local(state, {"query": "example"})
        self.assertFalse(result["library_known"])
        self.assertTrue(all(not r["in_plex"] for r in result["titles"]))
        self.assertEqual(
            len([r for r in result["titles"] if r["item"]["type"] == "movie"]), 2
        )

    def test_list_provider_search_paging_and_ignored_opt_in(self):
        state = self.state()
        state["settings"] = {"tmdb": {"key": "fixture"}}
        state["ignored_titles"] = [{"tokens": ["movie:tmdb:10"]}]
        payload = {
            "total_pages": 3,
            "results": [
                {
                    "id": 10,
                    "media_type": "movie",
                    "title": "The Example",
                    "release_date": "2020-01-01",
                },
                {"id": 20, "media_type": "tv", "name": "Example Show"},
                {
                    "id": 30,
                    "media_type": "person",
                    "name": "Person",
                    "profile_path": "/person.jpg",
                },
                {"id": 40, "media_type": "movie", "title": "Adult", "adult": True},
            ],
        }
        with patch("providers.cached_tmdb", return_value=payload) as get:
            result = search.remote(
                state, {"query": "example", "page": 2}, self.catalog(), True
            )
            self.assertEqual(len(result["items"]), 1)
            self.assertEqual(len(result["people"]), 1)
            self.assertTrue(result["has_more"])
            self.assertIn("page=2", get.call_args.args[0])
            self.assertEqual(
                len(
                    search.remote(state, {"query": "example", "include_ignored": True})[
                        "items"
                    ]
                ),
                2,
            )
        with patch("providers.peek_tmdb", return_value={}):
            local = search.local(
                state,
                {"query": "chronological"},
                official=[
                    {"id": "official", "name": "Chronological collection", "count": 4}
                ],
            )
        self.assertEqual(len(local["lists"]), 2)
        self.assertEqual(
            search.remote({"settings": {}}, {"query": "example"})["items"], []
        )

    def test_search_aliases_years_and_limits(self):
        self.assertIsNotNone(
            search.score("Marvel's Agents of S.H.I.E.L.D.", ["shield"])
        )
        self.assertIsNotNone(search.score("Teenage Mutant Ninja Turtles", ["tmnt"]))
        self.assertEqual(search.text("Pok\u00e9mon"), "pokemon")
        with patch("providers.peek_tmdb", return_value={}):
            self.assertEqual(
                len(search.local(self.state(), {"query": "example 2020"})["titles"]), 1
            )
        for body in (
            {"query": ""},
            {"query": " "},
            {"query": "x" * 121},
            {"query": []},
            {"query": "valid", "page": 101},
        ):
            with self.assertRaises(ValueError):
                search.local(self.state(), body)

    def test_unindexed_cache_peek_does_not_load_or_wait_on_library_scan(self):
        explore._library_cache.clear()
        settings = {"plex": {"url": "http://fixture", "key": "fixture"}}
        with explore._library_lock:
            self.assertEqual(explore.peek_library(settings), ([], False))
        self.assertEqual(explore.peek_library(settings), ([], False))
        with patch("time.time", return_value=100):
            explore.library(settings, lambda _: self.catalog())
        rows, known = explore.peek_library(settings)
        self.assertTrue(known)
        self.assertEqual(len(rows), 2)
        rows.clear()
        self.assertEqual(len(explore.peek_library(settings)[0]), 2)
        self.assertFalse(
            explore.peek_library({"plex": {"url": "http://other", "key": "fixture"}})[1]
        )
