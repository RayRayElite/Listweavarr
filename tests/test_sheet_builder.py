# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import text_list_builder as builder


class SheetBuilderTests(unittest.TestCase):
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
            result["text"], "Example | S02E03 | A title continued\nUnknown"
        )
        self.assertEqual(len(builder.infer(result["text"])), 2)
        with self.assertRaises(ValueError):
            builder.extract_sheet("Show,Episode,Title\n,,\n")

    def test_unknown_table_keeps_candidate_rows(self):
        result = builder.extract_sheet("Movie A (2001)\nMovie B (2002)\n")
        self.assertEqual(len(builder.infer(result["text"])), 2)

    def test_trailing_change_log_is_not_imported_as_episodes(self):
        result = builder.extract_sheet(
            "Show,Episode,Title\nExample,1x01,Pilot\n,,Change Log - notes\n,,Moved Example 1x01 after 1x02\n"
        )
        self.assertEqual(result["text"], "Example | 1x01 | Pilot")
        self.assertIn("Excluded", result["notice"])
