# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
from unittest.mock import patch
import issue_notebook as issues
import request_ledger
import backups
import list_sharing
import app


class IssueNotebookTests(unittest.TestCase):
    def state(self):
        return {
            "settings": {},
            "lists": [
                {
                    "id": "list",
                    "name": "Watch order",
                    "items": [
                        {
                            "id": "ep",
                            "type": "episode",
                            "title": "Pilot",
                            "show_title": "Show",
                            "show_tmdb": "20",
                            "season": "1",
                            "episode": "2",
                            "status": "available",
                        }
                    ],
                }
            ],
        }

    def body(self):
        return {
            "list_id": "list",
            "item_id": "ep",
            "note": "Subtitles disappear near 05:10.",
            "category": "subtitles",
            "severity": "high",
        }

    def test_scoped_note_is_private_and_does_not_change_media_or_request_state(self):
        state = self.state()
        original = copy.deepcopy(state["lists"])
        with patch(
            "providers.cached_tmdb",
            side_effect=AssertionError("Notes never call providers"),
        ), patch("providers.peek_tmdb", return_value={"poster_path": "/poster.jpg"}):
            saved = issues.save(state, self.body())
        self.assertEqual(saved["item"]["episode"], "2")
        self.assertTrue(saved["item"]["poster"].endswith("/poster.jpg"))
        self.assertEqual(state["lists"], original)
        self.assertNotIn("requests", state)
        self.assertNotIn("library_issues", list_sharing.export(state["lists"][0]))

    def test_resolution_reopening_and_revision_conflicts_keep_exact_identity(self):
        state = self.state()
        with patch("providers.peek_tmdb", return_value={}):
            created = issues.save(state, self.body())
            resolved = issues.save(
                state,
                {
                    **created,
                    "note": "Replaced subtitles. Fixed.",
                    "status": "resolved",
                    "item": {"type": "movie", "title": "Wrong", "tmdb": "99"},
                },
            )
            self.assertEqual(resolved["item"]["show_tmdb"], "20")
            with self.assertRaises(ValueError):
                issues.save(state, {**created, "note": "stale"})
            reopened = issues.save(
                state, {**resolved, "status": "open", "note": "Problem returned."}
            )
        self.assertEqual(
            [e["action"] for e in reopened["events"]],
            ["Created", "Resolved", "Reopened"],
        )

    def test_related_requests_use_exact_scope_and_reject_conflicting_ids(self):
        state = self.state()
        for episode in (1, 2):
            request_ledger.record(
                state,
                {
                    "type": "episode",
                    "title": "Episode",
                    "show_tmdb": "20",
                    "season": "1",
                    "episode": str(episode),
                },
                status="requested",
            )
        request_ledger.record(
            state, {"type": "show", "title": "Show", "tmdb": "20"}, status="requested"
        )
        with patch("providers.peek_tmdb", return_value={}):
            row = issues.save(state, self.body())
        self.assertEqual(len(row["requests"]), 1)
        self.assertFalse(
            issues.same_scope(
                {**row["item"], "show_imdb": "tt0000001"},
                {**row["item"], "show_imdb": "tt0000002"},
            )
        )

    def test_notebook_backup_round_trip_and_filters(self):
        state = self.state()
        with patch("providers.peek_tmdb", return_value={}):
            saved = issues.save(state, self.body())
            self.assertEqual(
                issues.listing(state, {"query": "05:10", "status": "all"})["total"], 1
            )
            document = backups.export(state)
            data, summary = backups.validate(document, app.normalize)
            self.assertEqual(summary["issues"], 1)
            restored = backups.restore({"lists": []}, data, "merge")
            self.assertEqual(restored["library_issues"][0]["note"], self.body()["note"])
            self.assertEqual(
                issues.listing(restored, {"item": saved["item"]})["total"], 1
            )
        malformed = copy.deepcopy(document)
        malformed["data"]["library_issues"][0]["item"][
            "unsupported_field"
        ] = "must not be retained"
        with self.assertRaises(ValueError):
            backups.validate(malformed, app.normalize)

    def test_show_and_season_views_include_child_issues_without_broadening_request_history(
        self,
    ):
        state = self.state()
        with patch("providers.peek_tmdb", return_value={}):
            issues.save(state, self.body())
            show = {"type": "show", "title": "Show", "tmdb": "20"}
            self.assertEqual(issues.listing(state, {"item": show})["total"], 1)
            season = {
                "type": "season",
                "title": "Season 1",
                "show_tmdb": "20",
                "season": "1",
            }
            self.assertEqual(issues.listing(state, {"item": season})["total"], 1)
            season["season"] = "2"
            self.assertEqual(issues.listing(state, {"item": season})["total"], 0)
            self.assertEqual(
                issues.listing(state, {"item": {**show, "tmdb": "99"}})["total"], 0
            )

    def test_manual_saved_scope_and_input_limits(self):
        state = self.state()
        item = state["lists"][0]["items"][0]
        item.pop("show_tmdb")
        with patch("providers.peek_tmdb", return_value={}):
            row = issues.save(state, self.body())
            self.assertEqual(
                issues.listing(
                    state, {"item": row["item"], "list_id": "list", "item_id": "ep"}
                )["total"],
                1,
            )
        for body in (
            {**self.body(), "note": ""},
            {**self.body(), "note": "x" * 5001},
            {**self.body(), "item_id": "removed"},
            {"item": {"type": "movie", "title": "Unknown"}, "note": "No ID"},
        ):
            with self.assertRaises(ValueError):
                issues.save(state, body)
