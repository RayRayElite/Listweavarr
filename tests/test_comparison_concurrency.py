# SPDX-License-Identifier: AGPL-3.0-only
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app


class ComparisonConcurrencyTests(unittest.TestCase):
    def test_remote_reads_release_state_lock_and_keep_new_request_logs(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.DATA", Path(folder)):
            app.save_state(
                {
                    "settings": {},
                    "lists": [
                        {
                            "id": "list",
                            "name": "List",
                            "items": [
                                {
                                    "id": "film",
                                    "title": "Film",
                                    "type": "movie",
                                    "tmdb": "1",
                                    "status": "missing",
                                }
                            ],
                            "playlist": {"fingerprint": "old"},
                        }
                    ],
                },
                backup=False,
            )

            def compare(rows, settings):
                self.assertTrue(
                    app.LOCK.acquire(blocking=False),
                    "Network read must not retain the state lock",
                )
                try:
                    changed = app.read_state()
                    changed["lists"][0]["items"][0]["request_log"] = {
                        "message": "New request"
                    }
                    app.save_state(changed)
                finally:
                    app.LOCK.release()
                return [
                    {
                        **rows[0],
                        "status": "available",
                        "plex_keys": ["10"],
                        "detail": "In Plex",
                    }
                ]

            with patch("app.compare", side_effect=compare):
                result = app.compare_saved_list("list")
            self.assertEqual(
                result["items"][0]["request_log"]["message"], "New request"
            )
            self.assertTrue(result["playlist_needs_update"])
            self.assertEqual(result["availability_report"][0]["to"], "available")

    def test_source_edit_during_compare_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.DATA", Path(folder)):
            app.save_state(
                {
                    "settings": {},
                    "lists": [
                        {
                            "id": "list",
                            "name": "List",
                            "items": [
                                {
                                    "id": "film",
                                    "title": "Film",
                                    "type": "movie",
                                    "tmdb": "1",
                                    "status": "missing",
                                }
                            ],
                        }
                    ],
                },
                backup=False,
            )

            def compare(rows, settings):
                changed = app.read_state()
                changed["lists"][0]["items"][0]["tmdb"] = "2"
                app.save_state(changed)
                return [{**rows[0], "status": "available", "plex_keys": ["10"]}]

            with patch("app.compare", side_effect=compare), self.assertRaisesRegex(
                ValueError, "changed during comparison"
            ):
                app.compare_saved_list("list")
            saved = app.read_state()["lists"][0]["items"][0]
            self.assertEqual((saved["tmdb"], saved["status"]), ("2", "missing"))
