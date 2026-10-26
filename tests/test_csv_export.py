"""Spreadsheet interchange preserves identities without leaking private state."""

import csv
import io
import unittest

import list_sharing


class CsvExportTests(unittest.TestCase):
    def test_order_scopes_and_private_fields(self):
        entry = {
            "name": "Order",
            "items": [
                {
                    "type": "episode",
                    "title": 'A, "quoted"\nname',
                    "show_tmdb": 7,
                    "season": 2,
                    "episode": 3,
                    "plex_key": "private",
                    "token": "secret",
                },
                {"type": "movie", "title": "Second", "tmdb": 9},
            ],
        }
        result = list_sharing.export_csv(entry)
        rows = list(csv.DictReader(io.StringIO(result["csv"])))
        self.assertEqual(rows[0]["title"], entry["items"][0]["title"])
        self.assertEqual(rows[0]["episode"], "3")
        self.assertEqual(rows[1]["tmdb"], "9")
        self.assertNotIn("private", result["csv"])
        self.assertNotIn("secret", result["csv"])

    def test_formula_escaping_and_empty_list(self):
        rows = list(
            csv.DictReader(
                io.StringIO(
                    list_sharing.export_csv(
                        {"name": "Example", "items": [{"title": " =HYPERLINK(1)"}]}
                    )["csv"]
                )
            )
        )
        self.assertEqual(rows[0]["title"], "' =HYPERLINK(1)")
        self.assertEqual(
            list(
                csv.DictReader(
                    io.StringIO(
                        list_sharing.export_csv({"name": "Empty", "items": []})["csv"]
                    )
                )
            ),
            [],
        )
