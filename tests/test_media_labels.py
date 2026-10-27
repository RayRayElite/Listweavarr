# SPDX-License-Identifier: AGPL-3.0-only
"""Catalogue annotations must not become titles or requested episode scopes."""
import unittest
import text_list_builder as builder


class MediaLabelTests(unittest.TestCase):
    def test_year_and_movie_labels(self):
        for title, label, year in [
            ("Jurassic Park", "1993 Movie", "1993"),
            ("The Lost World: Jurassic Park", "1997 Movie", "1997"),
            ("Battle at Big Rock", "2019 Short Film", "2019"),
            ("Dune: Part Three", "2026 Movie", "2026"),
            ("My Hero Academia: Two Heroes", "Movie 1", ""),
            ("My Hero Academia: You're Next", "Movie 4", ""),
            ("Example: Subtitle", "Movie 2020", "2020"),
        ]:
            with self.subTest(label=label, title=title):
                row = builder.infer(f"• {title} ({label})")[0]
                self.assertEqual(
                    (row["query"], row["type"], row["year"]), (title, "movie", year)
                )

    def test_dune_markdown_and_catalogue_counts(self):
        rows = builder.infer(
            "- [**Dune: Prophecy (2024 TV Series)**](https://example.org/search?q=dune) — 2 Seasons, 14 Episodes *(Takes place 10,000 years before the films)*\n"
            "- [**Dune: Part One (2021 Movie)**](https://example.org/)\n"
            "- **Dune: Part Two (2024 Movie)**"
        )
        self.assertEqual(
            [(r["query"], r["type"], r["year"]) for r in rows],
            [
                ("Dune: Prophecy", "show", "2024"),
                ("Dune: Part One", "movie", "2021"),
                ("Dune: Part Two", "movie", "2024"),
            ],
        )
        self.assertNotIn("episode", rows[0])

    def test_scopes_survive_placement_notes(self):
        rows = builder.infer(
            "Jurassic World: Camp Cretaceous — Seasons 2–5 (Takes place in the gap between Jurassic World and Fallen Kingdom)\n"
            "My Hero Academia: Season 5 — Episodes 19–25 (The Meta Liberation Army Arc)\n"
            "My Hero Academia: Season 8 (The Final Season)"
        )
        self.assertEqual(
            (rows[0]["query"], rows[0]["season"], rows[0]["season_end"]),
            ("Jurassic World: Camp Cretaceous", "2", "5"),
        )
        self.assertEqual(
            (
                rows[1]["query"],
                rows[1]["season"],
                rows[1]["episode"],
                rows[1]["episode_end"],
            ),
            ("My Hero Academia", "5", "19", "25"),
        )
        self.assertEqual(rows[2]["season"], "8")

    def test_specials_do_not_become_movies_or_inherit_previous_scope(self):
        rows = builder.infer(
            "My Hero Academia: Season 1\nMy Hero Academia: Save! Rescue Training! (OVA)\nMy Hero Academia: More (Epilogue OVA)\nMy Hero Academia: Vigilantes (Prequel Spin-Off Series)"
        )
        self.assertEqual([r["type"] for r in rows], ["season", "auto", "auto", "show"])
        self.assertEqual(rows[1]["query"], "My Hero Academia: Save! Rescue Training!")
        self.assertNotIn("season", rows[1])
        for label in ["Anime", "ONA", "Special", "TV Special"]:
            self.assertEqual(
                builder.infer(f"Example: Title ({label})")[0]["query"], "Example: Title"
            )

        self.assertEqual(
            builder.infer("My Hero Academia: HLB (Hero League Baseball) (OVA)")[0][
                "query"
            ],
            "My Hero Academia: HLB (Hero League Baseball)",
        )

    def test_missing_title_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "Missing title"):
            builder.infer(
                "• (2021 Short Film — The first half is set 65 million years ago)"
            )

    def test_boys_annotations_and_selected_episodes(self):
        rows = builder.infer(
            "- [**Vought Rising**](https://example.org/) (Upcoming Prequel Series) — Set in the 1950s\n"
            '- The Boys Presents: Diabolical — Episode 8: "One Plus One Equals Two" (Homelander prequel episode)\n'
            "- The Boys: Season 1 — Episodes 1–8\n"
            "- Butcher: A Short Film (5-minute short companion piece)\n"
            '- The Boys Presents: Diabolical — Episode 6: "Nubian vs Nubian" & Episode 7: "John and Sun-Hee"\n'
            "- Seven on 7 with Cameron Coleman (Web Series — Episodes 1–9)\n"
            "- Gen V: Season 2 — Episodes 1–8"
        )
        self.assertEqual(rows[0]["query"], "Vought Rising")
        self.assertEqual(rows[0]["type"], "show")
        self.assertEqual(rows[1]["episode"], "8")
        self.assertEqual(rows[1]["query"], "The Boys Presents: Diabolical")
        self.assertEqual(rows[3]["type"], "movie")
        self.assertEqual([r["episode"] for r in rows[4:6]], ["6", "7"])
        self.assertEqual(
            (rows[6]["query"], rows[6]["episode_end"]),
            ("Seven on 7 with Cameron Coleman", "9"),
        )
        self.assertEqual(
            (rows[7]["query"], rows[7]["season"], rows[7]["episode_end"]),
            ("Gen V", "2", "8"),
        )
