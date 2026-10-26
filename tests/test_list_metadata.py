# SPDX-License-Identifier: AGPL-3.0-only
import tempfile
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import app
import providers


class ListMetadataTests(unittest.TestCase):
    def test_many_episodes_share_parent_and_season_requests(self):
        calls = Counter()

        def tmdb(path, settings):
            calls[path] += 1
            if path == "tv/42":
                return {
                    "name": "Show",
                    "poster_path": "/poster.jpg",
                    "overview": "Series synopsis",
                }
            if path == "tv/42/season/1":
                return {
                    "episodes": [
                        {
                            "episode_number": n,
                            "name": "Episode " + str(n),
                            "overview": "Episode synopsis",
                            "vote_average": 8,
                            "vote_count": 50,
                            "air_date": "2020-01-01",
                            "runtime": 43,
                        }
                        for n in range(1, 21)
                    ]
                }
            raise AssertionError("List summaries must not request full episode credits")

        rows = [
            {
                "type": "episode",
                "title": "Entry",
                "tmdb": str(n + 100),
                "show_tmdb": "42",
                "season": "1",
                "episode": str(n),
            }
            for n in range(1, 21)
        ]
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch.object(providers, "CACHE", Path(folder)),
            patch.object(providers, "tmdb", side_effect=tmdb),
        ):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(
                    pool.map(
                        lambda row: providers.list_details(
                            row, {"tmdb": {"key": "test"}}
                        ),
                        rows,
                    )
                )
        self.assertEqual(calls, {"tv/42": 1, "tv/42/season/1": 1})
        self.assertTrue(all(r["summary_only"] for r in results))
        self.assertEqual(results[-1]["title"], "Episode 20")
        self.assertEqual(results[-1]["rating"], 8)
        self.assertEqual(
            results[-1]["poster"], "https://image.tmdb.org/t/p/w342/poster.jpg"
        )

    def test_missing_episode_is_not_replaced_with_another_episode(self):
        with patch.object(
            providers,
            "cached_tmdb",
            side_effect=[{"name": "Show"}, {"episodes": [{"episode_number": 1}]}],
        ):
            with self.assertRaisesRegex(ValueError, "not available"):
                providers.list_details(
                    {
                        "type": "episode",
                        "title": "Episode",
                        "tmdb": "123",
                        "show_tmdb": "42",
                        "season": "1",
                        "episode": "2",
                    },
                    {"tmdb": {"key": "test"}},
                )

    def test_empty_episode_synopsis_is_labeled_series_fallback(self):
        with patch.object(
            providers,
            "cached_tmdb",
            side_effect=[
                {"name": "Show", "overview": "Series overview"},
                {"episodes": [{"episode_number": 1, "name": "Pilot"}]},
            ],
        ):
            result = providers.list_details(
                {
                    "type": "episode",
                    "title": "Pilot",
                    "tmdb": "123",
                    "show_tmdb": "42",
                    "season": "1",
                    "episode": "1",
                },
                {"tmdb": {"key": "test"}},
            )
        self.assertEqual(result["overview_scope"], "series")
        self.assertEqual(result["overview"], "Series overview")
