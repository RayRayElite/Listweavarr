# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import text_list_builder as builder


class SheetBuilderTests(unittest.TestCase):
    def test_ncis_aliases_and_language_subheader(self):
        result = builder.extract_sheet(
            "#,Show,Episode,Title,\n,,,English,French\n1,NCIS: LA,8x01,High-Value Target,\n2,NCIS: NO,1x01,Pilot,\n"
        )
        self.assertNotIn("English", result["text"])
        self.assertIn("NCIS: Los Angeles | 8x01", result["text"])
        self.assertIn("NCIS: New Orleans | 1x01", result["text"])

    def test_workbook_preserves_tab_order_and_context(self):
        html = 'items.push({name: "2012: Fire S01, PD S01", pageUrl: "ignored", gid: "0"});items.push({name: "2013", pageUrl: "ignored", gid: "7"});'

        def fetch(url, default_show="", **kwargs):
            if kwargs.get("_raw"):
                return html
            self.assertEqual(default_show, "Chicago")
            return builder.extract_sheet(
                "Show,Episode,Title\nFire,"
                + ("1x01" if "gid=0" in url else "2x01")
                + ",Pilot\n",
                default_show=default_show,
            )

        with patch.object(builder, "fetch_page", side_effect=fetch):
            result = builder.fetch_workbook(
                "https://docs.google.com/spreadsheets/d/id/export?format=csv"
            )
        rows = builder.infer(result["text"])
        self.assertEqual([row["season"] for row in rows], ["1", "2"])
        self.assertEqual([row["query"] for row in rows], ["Chicago Fire"] * 2)
        self.assertEqual(len(result["worksheets"]), 2)

    def test_legend_is_not_imported(self):
        result = builder.extract_sheet(
            "#,Show,Episode,Title\n1,Fire,1x01,Pilot\nLegend,,,Made by\n,Chicago Fire,,\n",
            default_show="Chicago",
        )
        self.assertEqual(result["text"], "Chicago Fire | 1x01 | Pilot")

    def test_missing_tab_discovery_does_not_silently_import_partial_workbook(self):
        with self.assertRaises(ValueError):
            builder.sheet_tabs("<html>Sign in</html>")

    def test_selected_gid_and_safe_export(self):
        base = "https://docs.google.com/spreadsheets/d/abc_123/edit"
        self.assertEqual(
            builder.google_sheet_export(base + "#gid=123"),
            (
                "https://docs.google.com/spreadsheets/d/abc_123/export?format=csv&gid=123",
                "123",
            ),
        )
        self.assertEqual(builder.google_sheet_export(base + "?gid=45#gid=123")[1], "45")
        self.assertEqual(builder.google_sheet_export(base)[1], "0")
        self.assertIsNone(
            builder.google_sheet_export("https://example.com/spreadsheets/d/abc/edit")
        )
        for url in (
            base + "?gid=no",
            base.replace("https:", "http:"),
            base.replace("docs.google.com", "user@docs.google.com"),
        ):
            with self.assertRaises(ValueError):
                builder.google_sheet_export(url)

    def test_chicago_columns_ignore_notes_preserve_order_and_quoted_title(self):
        text = '#,Show,Episode,Title,Notes,Cameos\n,,,,,Fire\n594,Med,8x01,"How Do You Begin, Again?",private note,PD\n595,Fire,11x01,Hold on Tight,,\n596,PD,10x01,Let It Bleed,,\n'
        result = builder.extract_sheet(text, "1774113768")
        rows = builder.infer(result["text"])
        self.assertEqual(
            [r["query"] for r in rows], ["Chicago Med", "Chicago Fire", "Chicago P.D."]
        )
        self.assertEqual((rows[0]["season"], rows[0]["episode"]), ("8", "1"))
        self.assertIn("How Do You Begin, Again?", result["text"])
        self.assertNotIn("private note", result["text"])
        self.assertIn("1774113768", result["notice"])

    def test_generic_separate_season_episode_and_missing_scope(self):
        result = builder.extract_sheet(
            'Series,Season,Episode,Title\nExample,2,3,"A title\ncontinued"\nOther,,,Unknown\n'
        )
        self.assertEqual(
            result["text"],
            "Example | S02E03 | A title continued\nOther | Episode title: Unknown",
        )
        self.assertEqual(len(builder.infer(result["text"])), 2)
        with self.assertRaises(ValueError):
            builder.extract_sheet("Show,Episode,Title\n,,\n")

    def test_custom_release_codes_are_not_episode_numbers(self):
        result = builder.extract_sheet(
            "Release Order,Code,,Show,Name,Release Date,Date,Number\n"
            '1,CSI101,9,CSI: Crime Scene Investigation,"""Pilot""",10/6/2000,36805,101\n'
            '2,CSI103,9,CSI: Crime Scene Investigation,"""Cool Change""",10/13/2000,36812,103\n'
            '3,WAT303,10,Without a Trace,"""Pilot""",9/26/2002,37525,303\n'
        )
        rows = builder.infer(result["text"])
        self.assertEqual(
            [r["episode_title"] for r in rows], ["Pilot", "Cool Change", "Pilot"]
        )
        self.assertEqual(
            [r["query"] for r in rows],
            ["CSI: Crime Scene Investigation"] * 2 + ["Without a Trace"],
        )
        self.assertTrue(all(r["episode_catalogue"] for r in rows))
        self.assertTrue(all("episode" not in r for r in rows))
        self.assertNotIn("CSI103", result["text"])

    def test_title_only_catalogue_checks_later_seasons_and_keeps_ambiguity(self):
        row = builder.infer('Example | Episode title: "Season 1 (2)"')[0]
        parent = {"tmdb": "9", "type": "show", "title": "Example"}

        def metadata(path, settings):
            if path == "tv/9":
                return {"seasons": [{"season_number": n} for n in range(1, 5)]}
            return (
                {"episodes": [{"id": 10, "episode_number": 7, "name": "Season 1 (2)"}]}
                if path.endswith(("/3", "/4"))
                else {"episodes": []}
            )

        with patch("providers.cached_tmdb", side_effect=metadata):
            choices = builder.named_scopes(row, parent, {})
        self.assertEqual([c["scope"]["season"] for c in choices], ["3", "4"])
        self.assertEqual(row["episode_title"], "Season 1 (2)")

    def test_catalogue_title_variants_and_split_story(self):
        def metadata(path, settings):
            if path == "tv/9":
                return {"seasons": [{"season_number": 1}]}
            return {
                "episodes": [
                    {"id": 1, "episode_number": 1, "name": "The Storm (1)"},
                    {"id": 2, "episode_number": 2, "name": "The Storm (2)"},
                    {"id": 3, "episode_number": 3, "name": "Blood and Water"},
                ]
            }

        parent = {"tmdb": "9", "type": "show", "title": "Example"}
        with patch("providers.cached_tmdb", side_effect=metadata):
            for title, first, last in [
                ("The Storm (Part II)", "2", "2"),
                ("Storm", "1", "2"),
                ("Blood & Water", "3", "3"),
            ]:
                row = builder.infer("Example | Episode title: " + title)[0]
                choices = builder.named_scopes(row, parent, {})
                self.assertEqual(len(choices), 1)
                self.assertEqual(
                    (
                        choices[0]["scope"]["episode"],
                        choices[0]["scope"]["episode_end"],
                    ),
                    (first, last),
                )
            row = builder.infer("Example | Episode title: Blod and Water")[0]
            self.assertEqual(builder.named_scopes(row, parent, {}), [])

    def test_unknown_table_keeps_candidate_rows(self):
        result = builder.extract_sheet("Movie A (2001)\nMovie B (2002)\n")
        self.assertEqual(len(builder.infer(result["text"])), 2)

    def test_trailing_change_log_is_not_imported_as_episodes(self):
        result = builder.extract_sheet(
            "Show,Episode,Title\nExample,1x01,Pilot\n,,Change Log - notes\n,,Moved Example 1x01 after 1x02\n"
        )
        self.assertEqual(result["text"], "Example | 1x01 | Pilot")
        self.assertIn("Excluded", result["notice"])
