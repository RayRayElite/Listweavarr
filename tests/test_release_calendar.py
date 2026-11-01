# SPDX-License-Identifier: AGPL-3.0-only
import copy
import datetime
import unittest
from unittest.mock import patch
import release_calendar as calendar
import trakt_features

TODAY = datetime.date(2026, 10, 31)


class ReleaseCalendarTests(unittest.TestCase):
    def setUp(self):
        calendar._trakt_cache.clear()
        self.state = {
            "settings": {},
            "release_region": "CA",
            "release_watchlist": [
                {
                    "type": "movie",
                    "tmdb": "1",
                    "title": "Movie",
                    "region": "CA",
                    "digital_date": "2026-11-09",
                }
            ],
            "creator_follows": [{"id": "10", "name": "Actor", "role": "cast"}],
            "lists": [
                {
                    "id": "list",
                    "name": "Watch order",
                    "followed": True,
                    "items": [
                        {"type": "movie", "tmdb": "1", "title": "Movie"},
                        {
                            "type": "episode",
                            "show_tmdb": "2",
                            "show_title": "Show",
                            "title": "Episode",
                            "season": "1",
                            "episode": "2",
                        },
                    ],
                },
                {
                    "id": "unfollowed",
                    "name": "Private",
                    "followed": False,
                    "items": [{"type": "movie", "tmdb": "99", "title": "Ignore"}],
                },
            ],
        }
        self.cache = {
            "movie/1": {"release_date": "2026-11-01", "poster_path": "/movie.jpg"},
            "movie/1/release_dates": {
                "results": [
                    {
                        "iso_3166_1": "US",
                        "release_dates": [{"type": 4, "release_date": "2026-11-02"}],
                    },
                    {
                        "iso_3166_1": "CA",
                        "release_dates": [
                            {"type": 3, "release_date": "2026-11-01"},
                            {"type": 4, "release_date": "2026-11-10"},
                            {"type": 5, "release_date": "2026-11-12"},
                        ],
                    },
                ]
            },
            "tv/2": {"name": "Show", "poster_path": "/show.jpg"},
            "tv/2/season/1": {
                "episodes": [
                    {
                        "episode_number": 1,
                        "name": "Unselected",
                        "air_date": "2026-11-03",
                    },
                    {"episode_number": 2, "name": "Episode", "air_date": "2026-11-04"},
                    {"episode_number": 3, "name": "Undated", "air_date": None},
                ]
            },
            "person/10/combined_credits": {
                "cast": [
                    {
                        "id": 1,
                        "media_type": "movie",
                        "title": "Movie",
                        "release_date": "2026-11-01",
                    }
                ],
                "crew": [
                    {
                        "id": 88,
                        "media_type": "movie",
                        "title": "Crew-only",
                        "release_date": "2026-11-01",
                    }
                ],
            },
        }

    def test_cached_view_unifies_provenance_and_keeps_formats_and_scopes_distinct(self):
        original = copy.deepcopy(self.state)
        with patch(
            "providers.peek_tmdb", side_effect=lambda path: self.cache.get(path, {})
        ), patch(
            "providers.cached_tmdb",
            side_effect=AssertionError("Cached view must not call providers"),
        ), patch(
            "trakt_features.calendar",
            side_effect=AssertionError("Cached view must not call Trakt"),
        ):
            result = calendar.build(self.state, "2026-11", today=TODAY)
        self.assertEqual(len(result["items"]), 4)
        movie = [r for r in result["items"] if r["item"]["type"] == "movie"]
        self.assertEqual(
            {r["release_kind"] for r in movie}, {"theatrical", "digital", "disc"}
        )
        self.assertTrue(all(r["region"] == "CA" for r in movie))
        self.assertTrue(
            all(
                {s["type"] for s in r["sources"]}
                == {"watchlist", "followed", "creators"}
                for r in movie
            )
        )
        self.assertNotIn(
            "2026-11-09",
            {r["date"] for r in result["items"]},
            "New provider dates supersede the old tracked date",
        )
        episode = next(r for r in result["items"] if r["item"]["type"] == "episode")
        self.assertEqual(str(episode["item"]["episode"]), "2")
        self.assertEqual(episode["item"]["show_title"], "Show")
        self.assertEqual(self.state, original)

    def test_unknown_dates_are_omitted_and_watchlist_snapshots_work_offline(self):
        with patch("providers.peek_tmdb", return_value={}):
            result = calendar.build(self.state, "2026-11", today=TODAY)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["release_kind"], "digital")
        self.assertTrue(result["warnings"])

    def test_refresh_is_bounded_and_remote_failure_keeps_cached_dates(self):
        self.state["settings"] = {"tmdb": {"key": "fixture"}}
        with patch(
            "providers.peek_tmdb", side_effect=lambda path: self.cache.get(path, {})
        ), patch("providers.cached_tmdb", side_effect=ValueError("offline")) as get:
            result = calendar.build(self.state, "2026-11", True, today=TODAY)
        self.assertEqual(
            get.call_count, 1, "Do not repeatedly timeout against an offline provider"
        )
        self.assertEqual(len(result["items"]), 4)
        self.assertTrue(result["warnings"])
        self.state["lists"][0]["items"] = [
            {"type": "movie", "tmdb": str(i), "title": "Movie"} for i in range(1, 100)
        ]
        with patch("providers.peek_tmdb", return_value={}), patch(
            "providers.cached_tmdb", return_value={}
        ) as get:
            result = calendar.build(self.state, "2026-11", True, today=TODAY)
        self.assertLessEqual(get.call_count, 50)
        self.assertTrue(any("50" in w for w in result["warnings"]))

    def test_trakt_snapshot_survives_navigation_and_is_not_reused_after_unfollow(self):
        self.state["settings"] = {"trakt": {"key": "fixture"}}
        item = {
            "type": "episode",
            "show_tmdb": "2",
            "show_title": "Show",
            "title": "Trakt episode",
            "season": 1,
            "episode": 5,
            "release_date": "2026-11-20",
        }
        with patch("providers.peek_tmdb", return_value={}), patch(
            "trakt_features.calendar", return_value={"items": [item]}
        ) as get:
            result = calendar.build(self.state, "2026-11", True, today=TODAY)
            self.assertEqual(get.call_args.kwargs["days"], 30)
            cached = calendar.build(self.state, "2026-11", today=TODAY)
            self.assertEqual(len(cached["items"]), len(result["items"]))
            self.state["lists"][0]["followed"] = False
            empty = calendar.build(self.state, "2026-11", today=TODAY)
            self.assertFalse(
                any(r["item"]["type"] == "episode" for r in empty["items"])
            )

    def test_partial_calendar_failure_keeps_successful_tv_dates_and_ignores_hidden_titles(
        self,
    ):
        self.state["settings"] = {"trakt": {"key": "fixture"}}
        episode = {
            "type": "episode",
            "show_tmdb": "2",
            "show_title": "Show",
            "title": "New episode",
            "season": 1,
            "episode": 5,
            "release_date": "2026-11-20",
        }
        with patch("providers.peek_tmdb", return_value={}), patch(
            "trakt_features.calendar",
            return_value={
                "items": [episode],
                "warnings": ["Trakt movie dates could not be checked."],
            },
        ):
            result = calendar.build(self.state, "2026-11", True, today=TODAY)
            self.assertTrue(
                any(r["item"]["type"] == "episode" for r in result["items"])
            )
            self.state["ignored_titles"] = [{"tokens": ["show:tmdb:2"]}]
            hidden = calendar.build(self.state, "2026-11", today=TODAY)
            self.assertFalse(
                any(r["item"]["type"] == "episode" for r in hidden["items"])
            )

    def test_month_validation_and_leap_year(self):
        self.assertEqual(
            calendar.month_window("2028-02", datetime.date(2027, 1, 1))[1].day, 29
        )
        for value in ("2026-13", "bad", "2020-01", "2026-1", [2026, 11]):
            with self.assertRaises(ValueError):
                calendar.month_window(value, TODAY)

    def test_trakt_month_includes_first_and_last_day_and_preserves_partial_failure(
        self,
    ):
        lists = [{"followed": True, "items": [{"type": "show", "tmdb": "2"}]}]
        records = [
            {
                "first_aired": f"2026-11-{day}T20:00:00Z",
                "show": {"title": "Show", "ids": {"tmdb": 2}},
                "episode": {
                    "season": 1,
                    "number": int(day),
                    "title": "Episode",
                    "ids": {"trakt": int(day)},
                },
            }
            for day in ("01", "30")
        ]
        with patch(
            "trakt_features.cached_get", return_value={"data": records}
        ) as get, patch("providers.peek_tmdb", return_value={}):
            result = trakt_features.calendar(
                {},
                lists,
                start=datetime.date(2026, 11, 1),
                days=30,
                artwork_refresh=False,
            )
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(get.call_args.args[0].endswith("/2026-11-01/30"))
