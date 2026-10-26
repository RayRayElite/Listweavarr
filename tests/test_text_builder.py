# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import app
import text_list_builder as builder


class TextBuilderTests(unittest.TestCase):
    def test_extract_article_skips_scripts_and_keeps_table_order(self):
        html = "<title>Guide</title><nav>Noise</nav><article><h2>Marvel</h2><p>Film (2011)</p><table><tr><td>1</td><td>Arrow</td><td>S01E01</td><td>Pilot</td></tr></table><script>bad()</script></article><footer>Footer</footer>"
        result = builder.extract_html(html)
        self.assertEqual(result["title"], "Guide")
        self.assertIn("1 | Arrow | S01E01 | Pilot", result["text"])
        self.assertNotIn("Noise", result["text"])
        self.assertNotIn("bad()", result["text"])
        rows = builder.infer(result["text"])
        self.assertEqual(rows[-1]["query"], "Arrow")
        self.assertEqual(rows[-1]["episode"], "1")

    def test_mixed_order_ranges_and_source_evidence(self):
        rows = builder.infer(
            "1. Film (2011)\n2. Arrow S01E01-E03\n3. Other Show Season 2 episodes 4-5\n4. Last Show Seasons 1-2"
        )
        self.assertEqual(
            [r["type"] for r in rows], ["auto", "episode", "episode", "season"]
        )
        self.assertEqual(rows[0]["query"], "Film")
        self.assertEqual(rows[0]["year"], "2011")
        self.assertEqual(rows[1]["episode_end"], "3")
        self.assertEqual(rows[-1]["season"], "1")
        self.assertEqual(rows[-1]["season_end"], "2")
        self.assertEqual(rows[1]["raw"], "2. Arrow S01E01-E03")

    def test_pokemon_ranges_context_parts_and_horizons(self):
        from pathlib import Path

        text = (
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/provider-samples/pokemon-text-list.txt"
        ).read_text(encoding="utf-8-sig")
        rows = builder.infer(text)
        self.assertEqual(
            len(rows), len(text.strip().splitlines()) + 1
        )  # Two explicitly named Victini movie versions.
        self.assertEqual(rows[0]["type"], "episode")
        self.assertEqual(builder.plain(rows[0]["query"]), "pokemon")
        self.assertEqual(
            (rows[0]["season"], rows[0]["episode"], rows[0]["episode_end"]),
            ("1", "1", "69"),
        )
        self.assertEqual(builder.plain(rows[2]["query"]), "pokemon")
        part = next(row for row in rows if "Season 16 Part 2" in row["raw"])
        self.assertEqual((part["episode"], part["episode_end"]), ("26", "45"))
        self.assertIn("continuation", part["hint"])
        self.assertEqual(builder.plain(rows[-1]["query"]), "pokemon horizons")
        self.assertEqual(rows[-1]["numbering"], "absolute")
        self.assertEqual(rows[-1]["episode_end"], "147")
        self.assertEqual(rows[1]["type"], "movie")
        self.assertNotIn("Movie:", rows[1]["query"])
        self.assertNotIn("/", rows[1]["query"])
        chronicles = next(
            row for row in rows if "Mini Series: Chronicles" in row["raw"]
        )
        self.assertEqual(chronicles["type"], "episode")
        self.assertIn("Chronicles", chronicles["query"])
        self.assertEqual((chronicles["season"], chronicles["episode_end"]), ("1", "22"))

    def test_general_context_and_explicit_numbering(self):
        rows = builder.infer(
            "Season 2 Label (Ep. 46 to 89)", "Example Anime", "absolute"
        )
        self.assertEqual(rows[0]["query"], "Example Anime")
        self.assertEqual(rows[0]["episode_end"], "89")
        self.assertEqual(rows[0]["numbering"], "absolute")
        with patch(
            "providers.cached_tmdb",
            return_value={"seasons": [{"season_number": 1, "episode_count": 150}]},
        ):
            result = builder.scope_proposal(rows[0], {"type": "show", "tmdb": "9"}, {})
        self.assertEqual(result["scope"]["season"], "1")
        self.assertEqual(result["scope"]["episode"], "46")
        self.assertIn("absolute", result["scope_note"])

    def test_british_series_and_spinoff_context_are_isolated(self):
        from pathlib import Path

        text = (
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/provider-samples/doctor-who-text-list.txt"
        ).read_text(encoding="utf-8")
        rows = builder.infer(text)
        self.assertEqual(len(rows), 73)
        self.assertEqual(
            (rows[0]["query"], rows[0]["type"], rows[0]["season"], rows[0]["year"]),
            ("Doctor Who", "season", "1", "2005"),
        )
        torchwood = next(
            row for row in rows if row["raw"].lower() == "- torchwood: series 1"
        )
        self.assertEqual((torchwood["query"], torchwood["season"]), ("Torchwood", "1"))
        after = next(
            row for row in rows if row.get("episode_title") == "The Runaway Bride"
        )
        self.assertEqual(after["query"], "Doctor Who")
        series3 = next(row for row in rows if row["raw"] == "- Series 3, episodes 1-5")
        self.assertEqual(
            (series3["query"], series3["season"], series3["episode_end"]),
            ("Doctor Who", "3", "5"),
        )
        series5 = next(row for row in rows if row["raw"].startswith("- Series 5 ("))
        self.assertEqual(series5["type"], "season")
        self.assertEqual(series5["season"], "5")
        self.assertNotIn("episode", series5)
        infinite = next(
            row for row in rows if row.get("episode_title") == "The Infinite Quest"
        )
        self.assertNotIn("episode", infinite)
        self.assertEqual(infinite["query"], "Doctor Who")
        self.assertIn("source_note", infinite)
        sarah = next(
            row for row in rows if row.get("episode_title") == "Invasion of the Bane"
        )
        self.assertEqual(sarah["query"], "The Sarah Jane Adventures")
        born = next(row for row in rows if row.get("episode_title") == "Born Again")
        self.assertIn("2005 Children in Need special", born["episode_aliases"])
        finale = next(
            row for row in rows if row.get("episode_title") == "The End of Time"
        )
        self.assertEqual(finale["episode_parts"], [1, 2])
        pond = next(row for row in rows if row.get("episode_title") == "Pond Life")
        self.assertEqual(pond["episode_parts"], [1, 2, 3, 4, 5])
        self.assertEqual(
            builder.infer("Series 1", "Doctor Who (1963)")[0]["year"], "1963"
        )

    def test_british_scope_does_not_read_numbers_from_notes(self):
        rows = builder.infer(
            "Series 2 (All 13 episodes, with extras)\nSeries 3, episodes 6-13 (before series 4 episode 2)\n'Named Special' (released before series 5, episode 6)",
            "Example",
        )
        self.assertEqual(rows[0]["type"], "season")
        self.assertEqual(rows[1]["episode_end"], "13")
        self.assertEqual(rows[2]["episode_title"], "Named Special")
        self.assertNotIn("episode", rows[2])

    def test_exact_named_specials_arcs_and_parts_use_catalogue_numbers(self):
        parent = {"type": "show", "tmdb": "9", "title": "Example", "year": "2005"}

        def metadata(path, settings):
            if path == "tv/9":
                return {
                    "seasons": [
                        {"season_number": 0, "name": "Specials"},
                        {"season_number": 3, "name": "Children of Earth"},
                    ]
                }
            if path == "tv/9/season/0":
                return {
                    "episodes": [
                        {"id": index, "episode_number": index, "name": name}
                        for index, name in enumerate(
                            [
                                "Charity: Born Again",
                                "Finale (1)",
                                "Finale (2)",
                                "Space (1)",
                                "Time (2)",
                                "The Great Detective (Children in Need)",
                                "Vastra Investigates: A Christmas Prequel",
                            ],
                            1,
                        )
                    ]
                }
            raise ValueError("Unexpected lookup")

        with patch("providers.cached_tmdb", side_effect=metadata):
            single = builder.named_scopes({"episode_title": "Born Again"}, parent, {})
            self.assertEqual(single[0]["scope"]["episode"], "1")
            parts = builder.named_scopes(
                {"episode_title": "Finale", "episode_parts": [1, 2]}, parent, {}
            )
            self.assertEqual(
                (parts[0]["scope"]["episode"], parts[0]["scope"]["episode_end"]),
                ("2", "3"),
            )
            pair = builder.named_scopes(
                {
                    "episode_title": "Space / Time",
                    "episode_aliases": ["Space", "Time"],
                    "episode_parts": ["split"],
                },
                parent,
                {},
            )
            self.assertEqual(
                (pair[0]["scope"]["episode"], pair[0]["scope"]["episode_end"]),
                ("4", "5"),
            )
            for title, episode in [
                ("The Great Detective", "6"),
                ("Vastra Investigates", "7"),
            ]:
                self.assertEqual(
                    builder.named_scopes({"episode_title": title}, parent, {})[0][
                        "scope"
                    ]["episode"],
                    episode,
                )
            arc = builder.named_scopes(
                {"episode_title": "Children of Earth"}, parent, {}
            )
            self.assertEqual(arc[0]["scope"], {"type": "season", "season": "3"})
            self.assertEqual(
                builder.named_scopes({"episode_title": "Unknown"}, parent, {}), []
            )
            with patch.object(builder, "search", return_value=[parent]):
                result = builder.match_batch(
                    [
                        {
                            "query": "Example",
                            "type": "episode",
                            "episode_title": "Unknown",
                        }
                    ],
                    {},
                )
                self.assertIn("scope_error", result[0]["matches"][0])

    def test_direct_id_bypasses_search_and_requires_media_type(self):
        metadata = {"id": 123, "title": "Exact movie", "release_date": "2001-01-01"}
        with (
            patch("providers.cached_tmdb", return_value=metadata) as get,
            patch.object(builder, "search") as search,
        ):
            result = builder.match_batch(
                [
                    {
                        "tmdb_input": "123",
                        "query": "Cannot find this",
                        "type": "movie",
                        "year": "1900",
                        "episode_title": "Old inferred special",
                    }
                ],
                {},
            )
            self.assertEqual(result[0]["matches"][0]["tmdb"], "123")
            self.assertEqual(result[0]["matches"][0]["scope"]["type"], "movie")
            get.assert_called_once_with("movie/123", {})
            search.assert_not_called()
        result = builder.match_batch([{"tmdb_input": "123", "type": "auto"}], {})
        self.assertEqual(result[0]["matches"], [])
        self.assertIn("choose Movie", result[0]["error"])
        with patch("providers.cached_tmdb") as get:
            for value in (
                "0",
                "-1",
                "not-an-id",
                "https://example.com/movie/123",
                "https://user:password@www.themoviedb.org/movie/123",
            ):
                with self.assertRaises(ValueError):
                    builder.lookup_tmdb(value, "movie", {})
            get.assert_not_called()

    def test_tmdb_title_url_infers_media_and_episode_url_preserves_scope(self):
        def metadata(path, settings):
            if path == "movie/123":
                return {"id": 123, "title": "Movie"}
            if path == "tv/9":
                return {
                    "id": 9,
                    "name": "Show",
                    "seasons": [{"season_number": 0, "episode_count": 10}],
                }
            if path == "tv/9/season/0/episode/6":
                return {"id": 96, "name": "Special"}
            raise ValueError("Unknown record")

        with (
            patch("providers.cached_tmdb", side_effect=metadata),
            patch.object(builder, "search") as search,
        ):
            lookup = builder.lookup_tmdb(
                "https://www.themoviedb.org/movie/123-title", "auto", {}
            )
            self.assertEqual(lookup["type"], "movie")
            result = builder.match_batch(
                [
                    {
                        "query": "Unknown special",
                        "type": "auto",
                        "tmdb_input": "https://www.themoviedb.org/tv/9/season/0/episode/6",
                    }
                ],
                {},
            )
            scope = result[0]["matches"][0]["scope"]
            self.assertEqual(
                (scope["type"], scope["season"], scope["episode"]),
                ("episode", "0", "6"),
            )
            self.assertEqual(scope["episode_title"], "")
            search.assert_not_called()

    def test_numeric_movie_title_remains_a_name_search(self):
        with (
            patch.object(builder, "lookup_tmdb") as lookup,
            patch.object(builder, "search", return_value=[]) as search,
        ):
            builder.match_batch([{"query": "1917", "type": "movie"}], {})
            search.assert_called_once_with("1917", "movie", "", {})
            lookup.assert_not_called()

    def test_star_trek_checkboxes_quotes_parenthesized_seasons_and_named_pilots(self):
        from pathlib import Path

        text = (
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/provider-samples/star-trek-text-list.txt"
        ).read_text(encoding="utf-8-sig")
        rows = builder.infer(text)
        self.assertEqual(len(rows), 39)
        self.assertEqual(
            (
                rows[0]["query"],
                rows[0]["type"],
                rows[0]["season"],
                rows[0]["season_end"],
            ),
            ("Star Trek: Enterprise", "season", "1", "4"),
        )
        self.assertEqual(
            (rows[1]["query"], rows[1]["episode_title"]),
            ("Star Trek: The Original Series", "The Cage"),
        )
        self.assertEqual(rows[6]["query"], "Star Trek: The Motion Picture")
        self.assertEqual(rows[6]["type"], "auto")
        self.assertNotIn("episode_title", rows[6])
        self.assertEqual(rows[12]["query"], "Star Trek: The Next Generation")
        self.assertEqual(rows[12]["season_end"], "4")
        self.assertEqual(
            (
                rows[17]["type"],
                rows[17]["season"],
                rows[17]["episode"],
                rows[17]["episode_end"],
            ),
            ("episode", "3", "1", "9"),
        )
        self.assertEqual(
            (rows[-1]["query"], rows[-1]["episode_title"]),
            ("Star Trek: Short Treks", "Calypso"),
        )
        self.assertTrue(all("\u2611" not in row["query"] for row in rows))

    def test_season_ranges_verify_all_seasons_and_expand_in_order(self):
        def metadata(path, settings):
            if path == "tv/9":
                return {
                    "id": 9,
                    "name": "Show",
                    "seasons": [{"season_number": number} for number in range(1, 4)],
                }
            if path == "movie/7":
                return {"id": 7, "title": "Film"}
            if path.startswith("tv/9/season/"):
                number = int(path.rsplit("/", 1)[-1])
                if 1 <= number <= 3:
                    return {"id": 100 + number, "name": "Season " + str(number)}
            raise ValueError("Missing season")

        row = {
            "type": "season",
            "season": "1",
            "season_end": "3",
            "tmdb": "9",
            "confirmed": True,
        }
        with patch("providers.cached_tmdb", side_effect=metadata):
            proposal = builder.scope_proposal(row, {"type": "show", "tmdb": "9"}, {})
            self.assertEqual(proposal["scope"]["season_end"], "3")
            result = builder.confirmed_items(
                [row, {"type": "movie", "tmdb": "7", "confirmed": True}],
                {},
                app.normalize,
            )
            self.assertEqual(
                [value.get("season") for value in result], ["1", "2", "3", None]
            )
            self.assertEqual(result[-1]["type"], "movie")
            self.assertTrue(all(value["status"] == "unchecked" for value in result))
            row["season_end"] = "4"
            self.assertIn(
                "scope_error",
                builder.scope_proposal(row, {"type": "show", "tmdb": "9"}, {}),
            )
            with self.assertRaises(ValueError):
                builder.confirmed_items([row], {}, app.normalize)
            row["season_end"] = "0"
            with self.assertRaises(ValueError):
                builder.confirmed_items([row], {}, app.normalize)

    def test_original_series_alias_ranks_the_show_above_behind_the_scenes(self):
        metadata = {
            "results": [
                {
                    "id": 1,
                    "name": "Star Trek: The Original Series - The Roddenberry Vault",
                    "first_air_date": "2016-01-01",
                },
                {"id": 2, "name": "Star Trek", "first_air_date": "1966-01-01"},
            ]
        }
        with patch("providers.cached_tmdb", return_value=metadata):
            result = builder.search("Star Trek: The Original Series", "show", "", {})
        self.assertEqual(result[0]["tmdb"], "2")
        self.assertEqual(
            builder.parent_identity("Star Trek: The Original Series"),
            builder.parent_identity("Star Trek"),
        )

    def test_full_chicago_list_preserves_single_episode_scopes_and_order(self):
        import re
        from pathlib import Path

        text = (
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/provider-samples/chicago-text-list.txt"
        ).read_text(encoding="utf-8")
        lines = [
            (index, line)
            for index, line in enumerate(text.splitlines(), 1)
            if line.strip()
        ]
        rows = builder.infer(text)
        self.assertEqual(len(rows), 630)
        self.assertEqual(len(rows), len(lines))
        for row, (line_number, line) in zip(rows, lines):
            expected = re.search(r"(?i)S(\d+)E(\d+)", line)
            self.assertIsNotNone(expected)
            self.assertEqual(row["source_line"], line_number)
            self.assertEqual(row["type"], "episode")
            self.assertEqual(int(row["season"]), int(expected[1]))
            self.assertEqual(int(row["episode"]), int(expected[2]))
            self.assertEqual(row["episode_end"], row["episode"])
        row = next(row for row in rows if "8:30 PM" in row["raw"])
        self.assertEqual(
            (row["query"], row["episode"], row["episode_end"]),
            ("Chicago PD", "12", "12"),
        )

    def test_numeric_titles_are_not_episode_ranges_but_explicit_ranges_still_work(self):
        rows = builder.infer(
            "001. Show - S01E12 - 8:30 PM (Crossover 2/2)\n002. Show - S01E13 - 1984\n003. Show - S01E14 - 7\n004. Show - S02E01-E03 - A three part story\nShow S03E12 - 8:30 PM"
        )
        self.assertEqual(
            [row["episode_end"] for row in rows], ["12", "13", "14", "3", "12"]
        )
        self.assertTrue(all(row["query"] == "Show" for row in rows))

    def test_range_errors_distinguish_reversal_from_size(self):
        with self.assertRaisesRegex(ValueError, "ends before it starts"):
            builder.infer("Show S01E12-E08")
        with self.assertRaisesRegex(ValueError, "exceeds 3,000"):
            builder.infer("Show S01E01-E9999")

    def test_long_anime_range_stays_compact(self):
        rows = builder.infer("Season 1 (Ep 1-1200)", "Example Anime", "absolute")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["episode_end"], "1200")

    def test_scope_errors_preserve_source_instead_of_clipping(self):
        row = {"type": "episode", "season": "9", "episode": "39", "episode_end": "47"}
        with patch(
            "providers.cached_tmdb",
            return_value={"seasons": [{"season_number": 9, "episode_count": 46}]},
        ):
            result = builder.scope_proposal(row, {"type": "show", "tmdb": "9"}, {})
        self.assertIn("scope_error", result)
        self.assertEqual(row["episode_end"], "47")
        row["numbering"] = "absolute"
        with patch(
            "providers.cached_tmdb",
            return_value={
                "seasons": [
                    {"season_number": 1, "episode_count": 40},
                    {"season_number": 2, "episode_count": 50},
                ]
            },
        ):
            self.assertEqual(
                builder.scope_proposal(row, {"type": "show", "tmdb": "9"}, {})[
                    "scope_segments"
                ],
                [
                    {"season": "1", "episode": "39", "episode_end": "40"},
                    {"season": "2", "episode": "1", "episode_end": "7"},
                ],
            )

    def test_episode_range_expands_only_on_confirmed_save_preserving_order(self):
        def metadata(path, settings):
            if path == "tv/9":
                return {
                    "id": 9,
                    "name": "Example Anime",
                    "first_air_date": "2000-01-01",
                }
            if path == "movie/7":
                return {"id": 7, "title": "Film"}
            if path == "tv/9/season/1":
                return {
                    "id": 91,
                    "episodes": [
                        {
                            "id": number,
                            "episode_number": number,
                            "name": "Episode " + str(number),
                        }
                        for number in range(1, 5)
                    ],
                }
            raise ValueError("Unexpected path")

        rows = [
            {
                "confirmed": True,
                "type": "episode",
                "tmdb": "9",
                "season": "1",
                "episode": "1",
                "episode_end": "2",
            },
            {"confirmed": True, "type": "movie", "tmdb": "7"},
            {
                "confirmed": True,
                "type": "episode",
                "tmdb": "9",
                "season": "1",
                "episode": "3",
                "episode_end": "4",
            },
        ]
        with patch("providers.cached_tmdb", side_effect=metadata):
            saved = builder.confirmed_items(rows, {}, app.normalize)
            self.assertEqual(
                [row["type"] for row in saved],
                ["episode", "episode", "movie", "episode", "episode"],
            )
            self.assertEqual(saved[-1]["episode"], "4")
            rows[-1]["episode_end"] = "5"
            with self.assertRaisesRegex(ValueError, "no verified episode 5"):
                builder.confirmed_items(rows, {}, app.normalize)

    def test_ambiguous_lines_stay_reviewable(self):
        rows = builder.infer("This heading might be prose\nUnknown title\nShow 2x03")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["query"], "Show")
        self.assertEqual(rows[-1]["season"], "2")
        self.assertTrue(all("confirmed" not in row for row in rows))

    def test_reversed_and_oversized_ranges_rejected(self):
        for text in (
            "Show S1E5-E2",
            "Show S1E1-E9999",
            "Show S1E1-S2E3",
            "Show Seasons 3-1",
            "",
        ):
            with self.assertRaises(ValueError):
                builder.infer(text)

    def test_private_urls_and_redirect_targets_rejected(self):
        with patch(
            "socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]
        ):
            with self.assertRaisesRegex(ValueError, "public"):
                builder.public_target("https://example.com")
        for url in (
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com:8000",
        ):
            with self.assertRaises(ValueError):
                builder.public_target(url)

    def test_search_keeps_candidates_as_choices_excluding_people(self):
        with patch(
            "providers.cached_tmdb",
            return_value={
                "results": [
                    {"id": 1, "media_type": "person", "name": "Actor"},
                    {
                        "id": 2,
                        "media_type": "movie",
                        "title": "Film",
                        "release_date": "2020-01-01",
                    },
                    {
                        "id": 3,
                        "media_type": "tv",
                        "name": "Film",
                        "first_air_date": "2021-01-01",
                    },
                ]
            },
        ):
            rows = builder.search("Film", "auto", "", {})
        self.assertEqual([r["type"] for r in rows], ["movie", "show"])
        self.assertNotIn("confirmed", str(rows))

    def test_save_requires_confirmation_and_validates_episode(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            builder.confirmed_items([{"type": "movie", "tmdb": "1"}], {}, app.normalize)

        def metadata(path, settings):
            if path == "tv/2":
                return {"id": 2, "name": "Show", "first_air_date": "2001-01-01"}
            if path == "tv/2/season/1/episode/3":
                return {"id": 33, "name": "Episode Three"}
            raise ValueError("Invalid episode")

        with patch("providers.cached_tmdb", side_effect=metadata):
            rows = builder.confirmed_items(
                [
                    {
                        "confirmed": True,
                        "type": "episode",
                        "tmdb": "2",
                        "season": "1",
                        "episode": "3",
                    }
                ],
                {},
                app.normalize,
            )
            self.assertEqual(rows[0]["show_tmdb"], "2")
            self.assertNotIn("tmdb", rows[0])
            self.assertEqual(rows[0]["title"], "Episode Three")
            self.assertEqual(rows[0]["status"], "unchecked")
            with self.assertRaises(ValueError):
                builder.confirmed_items(
                    [
                        {
                            "confirmed": True,
                            "type": "episode",
                            "tmdb": "2",
                            "season": "1",
                            "episode": "99",
                        }
                    ],
                    {},
                    app.normalize,
                )


class BuilderHTTPTests(unittest.TestCase):
    def test_review_save_is_local_and_does_not_call_acquisition(self):
        import tempfile, threading, json, urllib.request, urllib.error
        from pathlib import Path

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(app, "DATA", Path(folder)),
        ):
            app.save_state(app.read_state())
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def post(action, body):
                request = urllib.request.Request(
                    "http://127.0.0.1:"
                    + str(server.server_port)
                    + (
                        action
                        if action.startswith("/")
                        else "/api/lists/build/" + action
                    ),
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    return json.load(response)

            try:
                with (
                    patch.object(app, "compare") as compare,
                    patch.object(app, "request_item") as acquire,
                    patch.object(
                        app.providers,
                        "cached_tmdb",
                        return_value={
                            "id": 7,
                            "title": "Example",
                            "release_date": "2001-01-01",
                        },
                    ),
                ):
                    state = app.read_state()
                    state["settings"]["tmdb"] = {"key": "test"}
                    app.save_state(state)
                    count = len(state["lists"])
                    looked_up = post(
                        "/api/lists/search", {"type": "movie", "tmdb_input": "7"}
                    )
                    self.assertEqual(looked_up["items"][0]["tmdb"], "7")
                    self.assertEqual(len(app.read_state()["lists"]), count)
                    preview = post("infer", {"text": "Example (2001)"})
                    self.assertEqual(preview["rows"][0]["query"], "Example")
                    self.assertEqual(len(app.read_state()["lists"]), count)
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        post(
                            "save",
                            {"name": "Test", "items": [{"type": "movie", "tmdb": "7"}]},
                        )
                    error.exception.close()
                    entry = post(
                        "save",
                        {
                            "name": "Test",
                            "reference": "https://example.com/order",
                            "items": [
                                {"confirmed": True, "type": "movie", "tmdb": "7"}
                            ],
                        },
                    )["entry"]
                    self.assertIsNone(entry["source"])
                    self.assertEqual(entry["items"][0]["status"], "unchecked")
                    self.assertEqual(len(app.read_state()["lists"]), count + 1)
                    compare.assert_not_called()
                    acquire.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
