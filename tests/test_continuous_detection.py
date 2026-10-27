# SPDX-License-Identifier: AGPL-3.0-only
"""Unseasoned named ranges become verified continuous episode scopes."""
from pathlib import Path
import unittest
from unittest.mock import patch
import app
import text_list_builder as builder


class ContinuousDetectionTests(unittest.TestCase):
    def test_naruto_ranges_and_movies_remain_distinct(self):
        text = (
            Path(__file__).parent / "fixtures/provider-samples/naruto-text-list.txt"
        ).read_text(encoding="utf-8")
        rows = builder.infer(text)
        episodes = [row for row in rows if row["type"] == "episode"]
        movies = [row for row in rows if row["type"] == "movie"]
        self.assertEqual(len(rows), 25)
        self.assertEqual(len(episodes), 14)
        self.assertEqual(len(movies), 11)
        self.assertTrue(all(row["numbering"] == "absolute" for row in episodes))
        self.assertEqual(episodes[-1]["query"], "Boruto: Naruto Next Generations")
        self.assertEqual(episodes[-1]["episode_end"], "293")
        self.assertTrue(
            any(row["query"] == "The Last: Naruto the Movie" for row in movies)
        )
        self.assertTrue(
            any(row["query"] == "Boruto: Naruto the Movie" for row in movies)
        )

    def metadata(self, path, settings):
        if path == "tv/9":
            return {
                "id": 9,
                "name": "Example",
                "seasons": [
                    {"season_number": 0, "episode_count": 99},
                    {"season_number": 1, "episode_count": 2},
                    {"season_number": 2, "episode_count": 3},
                ],
            }
        if path == "movie/3":
            return {"id": 3, "title": "Film"}
        parts = path.split("/")
        season = int(parts[3])
        count = 2 if season == 1 else 3
        episodes = [
            {"id": season * 100 + n, "episode_number": n, "name": f"S{season}E{n}"}
            for n in range(1, count + 1)
        ]
        if len(parts) == 4:
            return {
                "id": season * 10,
                "name": "Season " + str(season),
                "episodes": episodes,
            }
        return episodes[int(parts[-1]) - 1]

    def test_mapping_excludes_specials_and_preserves_movie_positions(self):
        rows = builder.infer(
            "Example (Episodes 2-4)\nFilm (movie)\nExample (Episodes 5-5)"
        )
        for row in rows:
            row.update(confirmed=True, tmdb="3" if row["type"] == "movie" else "9")
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            result = builder.confirmed_items(rows, {}, app.normalize)
        self.assertEqual(
            [(r["type"], r.get("season"), r.get("episode")) for r in result],
            [
                ("episode", "1", "2"),
                ("episode", "2", "1"),
                ("episode", "2", "2"),
                ("movie", None, None),
                ("episode", "2", "3"),
            ],
        )

    def test_explicit_seasons_stay_per_season_and_bad_totals_fail(self):
        row = builder.infer("Example (Season 2, Episodes 1-3)")[0]
        self.assertEqual(row["numbering"], "season")
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            proposal = builder.scope_proposal(
                builder.infer("Example (Episodes 1-6)")[0],
                {"tmdb": "9", "type": "show"},
                {},
            )
        self.assertIn("only 5 regular episodes", proposal["scope_error"])

    def test_seasons_can_keep_absolute_episode_identifiers(self):
        def metadata(path, settings):
            value = self.metadata(path, settings)
            if path == "tv/9/season/2":
                for episode in value["episodes"]:
                    episode["episode_number"] += 2
            return value

        row = builder.infer("Example (Episodes 2-4)")[0]
        row.update(confirmed=True, tmdb="9")
        with patch("providers.cached_tmdb", side_effect=metadata):
            result = builder.confirmed_items([row], {}, app.normalize)
        self.assertEqual(
            [(r["season"], r["episode"]) for r in result],
            [("1", "2"), ("2", "3"), ("2", "4")],
        )
