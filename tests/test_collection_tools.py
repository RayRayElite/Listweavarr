# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
import app
import collection_tools as tools


def movie(identifier, title=None):
    return {"type": "movie", "title": title or "Film " + identifier, "tmdb": identifier}


class CollectionToolsTests(unittest.TestCase):
    def original(self):
        return {
            "id": "copy",
            "name": "Personal title",
            "description": "Original",
            "poster": "",
            "official_id": "official",
            "official_version": 1,
            "items": [
                dict(
                    movie("1"), id="one", status="available", request_log={"kept": True}
                ),
                dict(movie("2"), id="two"),
                dict(movie("8"), id="custom"),
            ],
            "official_base": {
                "name": "Original title",
                "description": "Original",
                "poster": "",
                "items": [movie("1"), movie("2"), movie("3")],
            },
        }

    def update(self):
        return {
            "id": "official",
            "version": 2,
            "name": "New official title",
            "description": "Updated",
            "poster": "",
            "items": [movie("3"), movie("1"), movie("4")],
        }

    def test_merge_preserves_local_metadata_and_removals_but_removes_retired_base_entries(
        self,
    ):
        entry = self.original()
        before = copy.deepcopy(entry)
        result = tools.apply_update(entry, self.update(), "merge", app.normalize)
        self.assertEqual([row["tmdb"] for row in result["items"]], ["1", "4", "8"])
        self.assertEqual(result["name"], "Personal title")
        self.assertEqual(result["description"], "Updated")
        self.assertEqual(result["items"][0]["id"], "one")
        self.assertTrue(result["items"][0]["request_log"]["kept"])
        self.assertEqual(entry, before)
        self.assertEqual(result["official_version"], 2)

    def test_exact_mode_follows_official_order_and_keeps_matched_history(self):
        result = tools.apply_update(
            self.original(), self.update(), "replace", app.normalize
        )
        self.assertEqual([r["tmdb"] for r in result["items"]], ["3", "1", "4"])
        self.assertEqual(result["name"], "New official title")
        self.assertEqual(result["items"][1]["status"], "available")

    def test_old_copy_without_baseline_removes_nothing(self):
        entry = self.original()
        entry.pop("official_base")
        result = tools.apply_update(entry, self.update(), "merge", app.normalize)
        self.assertEqual(
            [r["tmdb"] for r in result["items"]], ["3", "1", "4", "2", "8"]
        )
        self.assertEqual(result["name"], "Personal title")

    def test_modified_retired_entry_is_preserved(self):
        entry = self.original()
        entry["items"][1]["title"] = "My label"
        result = tools.apply_update(entry, self.update(), "merge", app.normalize)
        self.assertIn("My label", [r["title"] for r in result["items"]])

    def test_rollback_preserves_recent_requests_and_playlist_reference(self):
        original = self.original()
        updated = tools.apply_update(original, self.update(), "merge", app.normalize)
        updated["items"][0]["request_log"] = {"new": "request"}
        updated["playlist"] = {"key": "latest"}
        restored = tools.rollback(updated)
        self.assertEqual([r["tmdb"] for r in restored["items"]], ["1", "2", "8"])
        self.assertEqual(restored["items"][0]["request_log"], {"new": "request"})
        self.assertEqual(restored["playlist"]["key"], "latest")
        self.assertTrue(restored["playlist_needs_update"])
        self.assertNotIn("official_undo", restored)

    def test_authors_and_stale_versions_are_not_overwritten(self):
        entry = self.original()
        entry["official_authoring"] = True
        with self.assertRaises(ValueError):
            tools.apply_update(entry, self.update(), "merge", app.normalize)
        entry.pop("official_authoring")
        entry["official_version"] = 2
        with self.assertRaises(ValueError):
            tools.apply_update(entry, self.update(), "merge", app.normalize)

    def test_duplicate_occurrences_survive_exact_update(self):
        official = self.update()
        official["items"] = [movie("1"), movie("1")]
        result = tools.apply_update(self.original(), official, "replace", app.normalize)
        self.assertEqual(len(result["items"]), 2)
        self.assertNotEqual(result["items"][0]["id"], result["items"][1]["id"])

    def test_health_is_read_only_and_gaps_are_review_notes(self):
        entry = {
            "name": "Order",
            "items": [
                dict(movie("1"), id="a"),
                dict(movie("1"), id="b"),
                {"type": "season", "show_tmdb": "9", "title": "Show", "season": "1"},
                {
                    "type": "episode",
                    "show_tmdb": "9",
                    "show_title": "Show",
                    "title": "Pilot",
                    "season": "1",
                    "episode": "1",
                },
                {
                    "type": "episode",
                    "show_tmdb": "9",
                    "title": "Three",
                    "season": "1",
                    "episode": "3",
                },
                {"type": "episode", "title": "Unmatched", "metadata_unresolved": True},
            ],
        }
        original = copy.deepcopy(entry)
        result = tools.health(entry)
        self.assertEqual(entry, original)
        for code in ("duplicate", "overlap", "gap", "unmatched", "scope"):
            self.assertIn(code, result["counts"])
        self.assertIn(
            "intentionally",
            next(r["message"] for r in result["issues"] if r["code"] == "gap"),
        )

    def test_preview_differences_and_order(self):
        result = tools.preview(self.original(), self.update())
        self.assertTrue(result["available"])
        self.assertTrue(result["has_baseline"])
        self.assertEqual(len(result["added"]), 2)
        self.assertEqual(len(result["removed"]), 2)
