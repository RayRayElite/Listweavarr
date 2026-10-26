# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
from unittest.mock import patch
import companion
import explore
import app
import saved_lists
import list_sharing
import collection_tools


def movie(key, minutes, genres=("Comedy", "Adventure"), year="2020"):
    return {
        "key": key,
        "type": "movie",
        "title": "Film " + key,
        "runtime": minutes,
        "genres": list(genres),
        "ids": {"tmdb": key},
        "year": year,
    }


def episode(number, minutes=25, season=1, watched=False):
    return {
        "key": "episode-" + str(number),
        "season": str(season),
        "episode": str(number),
        "runtime": minutes,
        "watched": watched,
    }


class DiscoverySessionTests(unittest.TestCase):
    def test_favorites_use_personal_ratings_and_replays_only(self):
        rows = [
            dict(movie("1", 90), watched=True, user_rating=9, view_count=1),
            dict(movie("2", 90), watched=True, user_rating=0, view_count=4),
            dict(movie("3", 90), watched=False, user_rating=10, view_count=0),
            dict(movie("4", 90), watched=True, user_rating=0, view_count=1),
        ]
        result = companion.favorites(rows, {})
        self.assertEqual({r["tmdb"] for r in result["items"]}, {"1", "2"})
        self.assertGreater(result["items"][0]["personal_rating"], 0)

    def test_separate_playlist_cover_survives_edit_and_sharing(self):
        import base64

        portrait = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\nportrait").decode()
        )
        square = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\nsquare").decode()
        )
        entry = {
            "id": "x",
            "name": "Test",
            "poster": portrait,
            "items": [],
            "playlist": {"key": "1"},
        }
        edited = saved_lists.edit(
            entry,
            {
                "revision": saved_lists.revision(entry),
                "name": "Test",
                "poster": portrait,
                "playlist_poster": square,
                "items": [],
            },
            app.normalize,
        )
        self.assertEqual(edited["poster"], portrait)
        self.assertTrue(edited["playlist_needs_update"])
        shared, _ = list_sharing.validate(list_sharing.export(edited), app.normalize)
        self.assertEqual(shared["playlist_poster"], square)
        self.assertEqual(shared["poster"], portrait)
        edited = saved_lists.edit(
            edited,
            {
                "revision": saved_lists.revision(edited),
                "name": "Renamed",
                "poster": portrait,
                "items": [],
            },
            app.normalize,
        )
        self.assertEqual(edited["playlist_poster"], square)

    def test_calendar_preserves_poster_and_parent_through_normalization(self):
        source = {
            "id": "1",
            "type": "episode",
            "title": "An episode",
            "show_title": "Parent show",
            "show_tmdb": "9",
            "tmdb": "12",
            "season": "1",
            "episode": "2",
            "poster": "https://image.tmdb.org/t/p/w342/test.jpg",
            "release_date": "2026-10-27",
        }
        with patch(
            "trakt_features.calendar",
            return_value={"items": [source], "warnings": [], "note": ""},
        ):
            result = app.release_calendar({"settings": {}, "lists": []})
        self.assertEqual(result["items"][0]["poster"], source["poster"])
        self.assertEqual(result["items"][0]["show_title"], "Parent show")

    def test_list_query_overrides_popular_mode(self):
        state = {"lists": [], "settings": {"trakt": {"key": "test"}}}
        with patch(
            "explore.trakt_features.search_lists",
            return_value={"lists": [], "has_more": False},
        ) as search:
            explore.lists(
                state, {"source": "trakt", "query": "tmnt", "mode": "popular"}
            )
        self.assertEqual(search.call_args.args[1:3], ("tmnt", "search"))

    def test_mood_home_filter_and_larger_result_pool(self):
        calls = []

        def tmdb(path, settings):
            calls.append(path)
            if path.startswith("genre/"):
                return {"genres": []}
            return {"results": [], "total_pages": 10}

        with patch("providers.cached_tmdb", side_effect=tmdb):
            companion.discover({"settings": {}}, {"release": "home"}, [])
        discover = [p for p in calls if p.startswith("discover/")]
        self.assertEqual(len(discover), 3)
        self.assertTrue(all("with_release_type=4%7C5" in p for p in discover))
        self.assertTrue(all("release_date.lte=" in p for p in discover))

    def test_franchise_priority_beats_closer_genre_runtime(self):
        rows = [movie("1", 50), movie("2", 50), movie("3", 59), movie("4", 60)]
        rows[0]["collection"] = rows[1]["collection"] = {"id": 9, "name": "Saga"}
        data = companion.tonight(rows, {"minutes": 120}, lambda *a: [], {})
        plans = [p for p in data["plans"] if p["kind"] == "movies"]
        self.assertEqual(plans[0]["strength"], 4)
        self.assertEqual({r["key"] for r in plans[0]["items"]}, {"1", "2"})

    def test_episode_run_is_sorted_consecutive_and_fits_budget(self):
        catalog = [
            {
                "key": "show",
                "type": "show",
                "title": "Series",
                "ids": {"tmdb": "9"},
                "runtime": 25,
            }
        ]
        leaves = [
            episode(4),
            episode(2),
            episode(1, watched=True),
            episode(3),
            episode(5),
        ]
        before = copy.deepcopy(catalog)
        result = companion.tonight(
            catalog, {"minutes": 80, "type": "show"}, lambda *a: leaves, {}
        )
        self.assertEqual(
            [r["episode"] for r in result["plans"][0]["items"]], ["2", "3", "4"]
        )
        self.assertEqual(result["plans"][0]["runtime"], 75)
        self.assertEqual(result["plans"][0]["remaining"], 5)
        self.assertEqual(result["items"][0]["episode"], "2")
        self.assertEqual(catalog, before)

    def test_episode_run_never_jumps_a_missing_episode(self):
        catalog = [
            {"key": "show", "type": "show", "title": "Series", "ids": {}, "runtime": 25}
        ]
        result = companion.tonight(
            catalog,
            {"minutes": 200},
            lambda *a: [episode(1), episode(3), episode(4)],
            {},
        )
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["plans"], [])

    def test_movie_double_feature_requires_a_connection(self):
        catalog = [
            movie("1", 70),
            movie("2", 80, year="2010"),
            movie("3", 70, ("Documentary",)),
        ]
        result = companion.tonight(
            catalog, {"minutes": 150, "type": "movie"}, lambda *a: [], {}
        )
        plans = result["plans"]
        self.assertEqual(len(plans), 1)
        self.assertEqual([r["key"] for r in plans[0]["items"]], ["2", "1"])
        self.assertEqual(plans[0]["runtime"], 150)
        self.assertIn("Shared genres", plans[0]["reason"])

    def test_collection_can_connect_movies_without_shared_genres(self):
        catalog = [movie("1", 50, ("Drama",)), movie("2", 60, ("Comedy",))]
        with patch(
            "providers.cached_tmdb",
            return_value={"belongs_to_collection": {"id": 9, "name": "Saga"}},
        ):
            result = companion.tonight(
                catalog, {"minutes": 120}, lambda *a: [], {"tmdb": {"key": "test"}}
            )
        self.assertEqual(result["plans"][0]["reason"], "Same collection: Saga")

    def test_movies_do_not_starve_tv_and_all_plans_fit(self):
        catalog = [movie(str(i), 40) for i in range(40)] + [
            {
                "key": "show",
                "type": "show",
                "title": "Series",
                "runtime": 20,
                "genres": ["Comedy"],
                "ids": {"tmdb": "999"},
            }
        ]
        result = companion.tonight(
            catalog,
            {"minutes": 120},
            lambda *a: [episode(i, 20) for i in range(1, 9)],
            {},
        )
        self.assertTrue(any(row["type"] == "episode" for row in result["items"]))
        self.assertTrue(any(plan["kind"] == "mixed" for plan in result["plans"]))
        self.assertTrue(
            any(
                len(plan["items"]) == 3 and plan["kind"] == "movies"
                for plan in result["plans"]
            )
        )
        for plan in result["plans"]:
            self.assertLessEqual(sum(row["runtime"] for row in plan["items"]), 120)
            self.assertEqual(
                len({row["key"] for row in plan["items"]}), len(plan["items"])
            )

    def test_watched_unknown_and_bad_runtime_titles_are_not_planned(self):
        a = movie("1", 40)
        a["watched"] = True
        result = companion.tonight(
            [a, movie("2", None), movie("3", 0), movie("4", -5)],
            {"minutes": 120},
            lambda *a: [],
            {},
        )
        self.assertEqual(result["items"], [])
        self.assertEqual(result["plans"], [])

    def test_recommended_order_is_portable_without_mutating_list(self):
        entry = {
            "id": "l",
            "name": "Order",
            "items": [
                dict(movie("1", 20), id="a", tmdb="1"),
                dict(movie("2", 20), id="b", tmdb="2"),
            ],
            "watch_paths": {"recommended": ["b", "a"], "chronological": ["a", "b"]},
        }
        before = copy.deepcopy(entry)
        shared = list_sharing.export(entry)
        restored, _ = list_sharing.validate(shared, app.normalize)
        rows, _ = companion.paths(restored, {"mode": "recommended"})
        self.assertEqual([row["tmdb"] for row in rows], ["2", "1"])
        self.assertEqual(entry, before)
        companion.validate_state({"lists": [restored]})

    def test_official_merge_adds_new_order_and_keeps_custom_order(self):
        items = [
            {"type": "movie", "title": "One", "tmdb": "1"},
            {"type": "movie", "title": "Two", "tmdb": "2"},
        ]
        entry = {
            "id": "local",
            "name": "Order",
            "items": [dict(items[0], id="a"), dict(items[1], id="b")],
            "official_id": "pub",
            "official_version": 1,
            "watch_paths": {"essential": ["b"]},
            "official_base": collection_tools.snapshot(
                {"name": "Order", "items": items}
            ),
        }
        official = {
            "id": "pub",
            "version": 2,
            "name": "Order",
            "items": items,
            "paths": {"recommended": [1, 0], "essential": [0]},
        }
        updated = collection_tools.apply_update(entry, official, "merge", app.normalize)
        self.assertEqual(updated["watch_paths"]["recommended"], ["b", "a"])
        self.assertEqual(updated["watch_paths"]["essential"], ["b"])

    def test_official_merge_updates_unchanged_curated_order(self):
        items = [
            {"type": "movie", "title": "One", "tmdb": "1"},
            {"type": "movie", "title": "Two", "tmdb": "2"},
        ]
        entry = {
            "id": "local",
            "name": "Order",
            "items": [dict(items[0], id="a"), dict(items[1], id="b")],
            "official_id": "pub",
            "official_version": 1,
            "watch_paths": {"recommended": ["a", "b"]},
            "official_base": collection_tools.snapshot(
                {"name": "Order", "items": items, "paths": {"recommended": [0, 1]}}
            ),
        }
        official = {
            "id": "pub",
            "version": 2,
            "name": "Order",
            "items": items,
            "paths": {"recommended": [1, 0]},
        }
        updated = collection_tools.apply_update(entry, official, "merge", app.normalize)
        self.assertEqual(updated["watch_paths"]["recommended"], ["b", "a"])

    def test_inbox_sorts_unique_events_and_supports_individual_read_state(self):
        state = {
            "lists": [],
            "requests": [
                {
                    "id": "old",
                    "item": {"title": "Old", "tmdb": "1", "type": "movie"},
                    "status": "available",
                    "updated_at": 100,
                },
                {
                    "id": "new",
                    "item": {"title": "New", "tmdb": "2", "type": "movie"},
                    "status": "available",
                    "updated_at": 200,
                },
            ],
            "inbox_seen": ["request:new:available"],
        }
        before = copy.deepcopy(state)
        with patch("official_lists.document", return_value={"lists": []}):
            rows = companion.inbox(state)
        self.assertEqual([row["title"] for row in rows], ["New", "Old"])
        self.assertTrue(rows[0]["read"])
        self.assertFalse(rows[1]["read"])
        self.assertEqual(state, before)

    def test_tracked_identity_distinguishes_movies_and_tv(self):
        state = {"release_watchlist": [{"type": "movie", "tmdb": "1"}]}
        self.assertTrue(explore.tracked({"type": "movie", "tmdb": 1}, state))
        self.assertFalse(explore.tracked({"type": "show", "tmdb": "1"}, state))
