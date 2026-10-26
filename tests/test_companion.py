# SPDX-License-Identifier: AGPL-3.0-only
import copy
import datetime
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import app
import companion as c
import backups


class CompanionTests(unittest.TestCase):
    def test_recipe_validation_and_filters(self):
        with self.assertRaises(ValueError):
            c.recipe({"year_from": 2020, "year_to": 2000})
        with self.assertRaises(ValueError):
            c.recipe({"minutes": 0, "type": "person"})
        catalog = [
            {
                "type": "movie",
                "title": "Owned",
                "ids": {"tmdb": "1"},
                "genres": ["Drama"],
            }
        ]
        calls = []

        def metadata(path, settings):
            calls.append(path)
            if path.startswith("genre/"):
                return {
                    "genres": [
                        {"id": 18, "name": "Drama"},
                        {"id": 35, "name": "Comedy"},
                    ]
                }
            if path.startswith("search/keyword"):
                return {"results": []}
            return {
                "results": [
                    {
                        "id": 1,
                        "title": "Owned",
                        "vote_average": 8,
                        "vote_count": 500,
                        "genre_ids": [18],
                    },
                    {
                        "id": 2,
                        "title": "New",
                        "vote_average": 8,
                        "vote_count": 500,
                        "genre_ids": [35],
                    },
                ]
            }

        with patch("providers.cached_tmdb", side_effect=metadata):
            result = c.discover(
                {"settings": {}, "explore_languages": ["en"]},
                {"tags": "missing theme", "minutes": 90, "genres": ["18"]},
                catalog,
            )
        self.assertEqual([r["tmdb"] for r in result["items"]], ["2"])
        self.assertIn("not used", result["warnings"][0])
        params = parse_qs(
            urlsplit(next(p for p in calls if p.startswith("discover/"))).query
        )
        self.assertEqual(params["with_runtime.lte"], ["90"])
        self.assertEqual(params["with_original_language"], ["en"])
        self.assertEqual(params["with_genres"], ["18"])

    def test_blind_spots_select_underrepresented_genres(self):
        def metadata(path, settings):
            return (
                {
                    "genres": [
                        {"id": 1, "name": "Drama"},
                        {"id": 2, "name": "Western"},
                        {"id": 3, "name": "Comedy"},
                        {"id": 4, "name": "Mystery"},
                    ]
                }
                if path.startswith("genre/")
                else {"results": []}
            )

        catalog = [{"type": "movie", "title": "A", "genres": ["Drama"], "ids": {}}] * 10
        with patch("providers.cached_tmdb", side_effect=metadata):
            result = c.discover({"settings": {}}, {}, catalog, True)
        self.assertNotIn("1", result["recipe"]["genres"])
        self.assertIn("blind spots", result["note"])

    def test_tonight_runtime_watched_and_next_episode(self):
        catalog = [
            {
                "key": "a",
                "type": "movie",
                "title": "Short",
                "runtime": 90,
                "ids": {"tmdb": "1"},
            },
            {
                "key": "b",
                "type": "movie",
                "title": "Watched",
                "runtime": 90,
                "watched": True,
                "ids": {},
            },
            {
                "key": "c",
                "type": "movie",
                "title": "Unknown",
                "runtime": None,
                "ids": {},
            },
            {
                "key": "show",
                "type": "show",
                "title": "Series",
                "runtime": 25,
                "ids": {"tmdb": "2"},
            },
        ]
        result = c.tonight(
            catalog,
            {"minutes": 100},
            lambda *args: [
                {"key": "e1", "season": "1", "episode": "1", "watched": True},
                {"key": "e2", "season": "1", "episode": "2", "watched": False},
            ],
            {},
        )
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][1]["episode"], "2")
        self.assertNotIn("Watched", [r["title"] for r in result["items"]])

    def test_tonight_caps_show_reads_even_without_unwatched_episodes(self):
        catalog = [
            {"key": str(i), "type": "show", "title": "Series", "ids": {}}
            for i in range(30)
        ]
        calls = []
        c.tonight(catalog, {}, lambda *a: (calls.append(a) or []), {})
        self.assertEqual(len(calls), 10)

    def test_storage_uses_manager_free_space_and_explicit_estimates(self):
        def call(settings, service, path):
            return (
                [{"path": "/movies", "freeSpace": 100 * 1024**3}]
                if path == "rootfolder"
                else [{"id": 1, "name": "HD"}]
            )

        state = {"settings": {"radarr": {"key": "key", "url": "http://nas"}}}
        options = c.storage(state, {}, call)
        self.assertEqual(options["profiles"][0]["id"], 1)
        result = c.storage(
            state,
            {"root": "/movies", "profile": 1, "count": 10, "low_gb": 2, "high_gb": 12},
            call,
        )
        self.assertEqual(result["high_gb"], 120)
        self.assertFalse(result["fits"])
        self.assertEqual(result["free_gb"], 100)

    def test_priorities_completion_and_no_mutation(self):
        state = {
            "lists": [
                {
                    "id": "a",
                    "name": "A",
                    "items": [
                        {
                            "id": "one",
                            "title": "One",
                            "type": "movie",
                            "status": "missing",
                        }
                    ],
                }
            ]
        }
        before = copy.deepcopy(state)
        result = c.priorities(state)
        self.assertEqual(result[0]["score"], 70)
        self.assertEqual(state, before)

    def test_paths_need_curated_essential_and_preserve_custom_order(self):
        entry = {
            "items": [
                {"id": "a", "title": "A", "year": "2020"},
                {"id": "b", "title": "B", "year": "1990"},
            ]
        }
        self.assertEqual(
            [r["id"] for r in c.paths(entry, {"mode": "release"})[0]], ["b", "a"]
        )
        with self.assertRaises(ValueError):
            c.paths(entry, {"mode": "essential"})
        entry["watch_paths"] = {"essential": ["b", "removed", "a"]}
        rows, stale = c.paths(entry, {"mode": "essential"})
        self.assertEqual([r["id"] for r in rows], ["b", "a"])
        self.assertEqual(stale, 1)

    def test_franchise_completion_distinguishes_owned_and_future(self):
        catalog = [
            {"type": "movie", "title": "Owned", "ids": {"tmdb": "1"}, "watched": True}
        ]

        def metadata(path, settings):
            if path.startswith("movie/"):
                return {"belongs_to_collection": {"id": 9}}
            return {
                "id": 9,
                "name": "Collection",
                "parts": [
                    {"id": 1, "title": "Owned", "release_date": "2000-01-01"},
                    {"id": 2, "title": "Missing", "release_date": "2001-01-01"},
                    {"id": 3, "title": "Future", "release_date": "2199-01-01"},
                ],
            }

        with patch("providers.cached_tmdb", side_effect=metadata):
            result = c.franchise({"settings": {}}, catalog)
        self.assertEqual(result["groups"][0]["missing"], 1)

    def test_feedback_report_correlations(self):
        state = {
            "discovery_impressions": {
                "movie:1": {"type": "movie", "tmdb": "1", "title": "A"}
            },
            "taste_feedback": {"movie:1": {"value": "like"}},
            "requests": [
                {"item": {"type": "movie", "tmdb": "1"}, "status": "available"}
            ],
        }
        result = c.report(
            state, [{"type": "movie", "ids": {"tmdb": "1"}, "watched": True}]
        )
        self.assertEqual(
            (result["recommended"], result["watched"], result["requested"]), (1, 1, 1)
        )

    def test_radar_role_date_and_dedup(self):
        state = {
            "settings": {},
            "creator_follows": [{"id": "9", "name": "Person", "role": "crew"}],
        }
        future = str(c.today() + datetime.timedelta(days=10))
        data = {
            "cast": [
                {
                    "id": 1,
                    "media_type": "movie",
                    "title": "Cast",
                    "release_date": future,
                }
            ],
            "crew": [
                {"id": 2, "media_type": "tv", "name": "Crew", "first_air_date": future}
            ]
            * 2,
        }
        with patch("providers.cached_tmdb", return_value=data):
            events, warnings = c.radar(state, lambda r: False)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Crew")

    def test_inbox_noise_and_read_flags(self):
        state = {
            "lists": [],
            "release_watchlist": [{"id": "a", "title": "Released", "status": "home"}],
            "inbox_seen": ["release:a:home"],
            "companion_preferences": {"muted_inbox": []},
        }
        with patch("official_lists.document", return_value={"lists": []}):
            rows = c.inbox(state)
        self.assertTrue(rows[0]["read"])
        state["companion_preferences"]["muted_inbox"] = ["releases"]
        with patch("official_lists.document", return_value={"lists": []}):
            self.assertEqual(c.inbox(state), [])

    def test_episode_group_mapping_checks_normal_ids_and_show_membership(self):
        def metadata(path, settings):
            return {
                "tv/9/episode_groups": {"results": [{"id": "group"}]},
                "tv/episode_group/group": {
                    "name": "DVD",
                    "groups": [
                        {
                            "id": "block",
                            "order": 1,
                            "episodes": [
                                {
                                    "id": 11,
                                    "order": 0,
                                    "season_number": 2,
                                    "episode_number": 1,
                                }
                            ],
                        }
                    ],
                },
                "tv/9": {"name": "Show"},
                "tv/9/season/2": {
                    "episodes": [{"id": 11, "episode_number": 1, "name": "Episode"}]
                },
            }[path]

        with patch("providers.cached_tmdb", side_effect=metadata):
            result = c.episode_map(
                {}, {"tmdb": "9", "group": "group", "first": 1, "last": 1}
            )
        self.assertEqual(result["items"][0]["season"], "2")
        with patch("providers.cached_tmdb", side_effect=metadata):
            with self.assertRaises(ValueError):
                c.episode_map(
                    {}, {"tmdb": "9", "group": "other", "first": 1, "last": 1}
                )

    def test_paths_are_portable_and_invalid_preference_backups_rejected(self):
        import list_sharing

        entry = {
            "id": "local",
            "name": "Paths",
            "items": [
                {"id": "a", "type": "movie", "title": "A", "tmdb": "1"},
                {"id": "b", "type": "movie", "title": "B", "tmdb": "2"},
            ],
            "watch_paths": {"essential": ["b", "a"]},
        }
        shared = list_sharing.export(entry)
        self.assertEqual(shared["list"]["paths"]["essential"], [1, 0])
        restored, _ = list_sharing.validate(shared, app.normalize)
        ids = restored["watch_paths"]["essential"]
        by_id = {r["id"]: r for r in restored["items"]}
        self.assertEqual([by_id[i]["tmdb"] for i in ids], ["2", "1"])
        bad = {
            "format": "reelcheck-workspace",
            "version": 1,
            "data": {"lists": [], "companion_preferences": {"spoiler_safe": "yes"}},
        }
        with self.assertRaises(ValueError):
            backups.validate(bad, app.normalize)
