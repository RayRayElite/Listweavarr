# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import app
import saved_lists


class ListManagementTests(unittest.TestCase):
    def entry(self, source=None):
        return {
            "id": "list",
            "name": "My order",
            "description": "Keep this",
            "poster": "original-poster",
            "source": source,
            "followed": bool(source),
            "playlist": {"key": "kept"},
            "items": [
                {
                    "id": "a",
                    "type": "movie",
                    "tmdb": "1",
                    "title": "One",
                    "status": "available",
                    "plex_keys": ["kept"],
                    "request_log": {"status": "requested"},
                },
                {
                    "id": "b",
                    "type": "episode",
                    "show_tmdb": "2",
                    "title": "Pilot",
                    "season": "1",
                    "episode": "1",
                    "status": "missing",
                },
            ],
        }

    def test_append_keeps_metadata_and_skips_exact_scope_duplicates(self):
        entry = self.entry()
        body = {"mode": "append", "revision": saved_lists.revision(entry)}
        added = [
            {"id": "duplicate", "type": "movie", "tmdb": "1", "title": "One"},
            {
                "id": "episode2",
                "type": "episode",
                "show_tmdb": "2",
                "season": "1",
                "episode": "2",
                "title": "Two",
                "status": "unchecked",
            },
            {
                "id": "same-again",
                "type": "episode",
                "show_tmdb": "2",
                "season": "1",
                "episode": "2",
                "title": "Two",
                "status": "unchecked",
            },
        ]
        result, report = saved_lists.update_entries(entry, added, body)
        self.assertEqual([row["id"] for row in result["items"]], ["a", "b", "episode2"])
        self.assertEqual(report["added"], 1)
        self.assertEqual(report["skipped"], 2)
        self.assertEqual(result["items"][0], entry["items"][0])
        self.assertEqual(result["poster"], "original-poster")
        self.assertEqual(result["description"], "Keep this")
        self.assertTrue(result["playlist_needs_update"])
        self.assertEqual(len(entry["items"]), 2)

    def test_replacement_preserves_matching_rows_and_uses_reviewed_order(self):
        entry = self.entry()
        rows = [
            dict(entry["items"][1], id="new-b"),
            {
                "id": "new",
                "type": "movie",
                "tmdb": "3",
                "title": "New",
                "status": "unchecked",
            },
        ]
        result, report = saved_lists.update_entries(
            entry, rows, {"mode": "replace", "revision": saved_lists.revision(entry)}
        )
        self.assertEqual([row["id"] for row in result["items"]], ["b", "new"])
        self.assertEqual(report["removed"], 1)
        self.assertEqual(report["added"], 1)
        self.assertEqual(result["items"][0]["status"], "missing")

    def test_linked_manual_update_requires_detachment_and_rejects_stale_edits(self):
        entry = self.entry("https://example.com/list")
        rows = [{"id": "c", "type": "movie", "tmdb": "3", "title": "New"}]
        body = {"mode": "append", "revision": saved_lists.revision(entry)}
        with self.assertRaisesRegex(ValueError, "linked list"):
            saved_lists.update_entries(entry, rows, body)
        result, _ = saved_lists.update_entries(
            entry, rows, dict(body, confirm_detach=True)
        )
        self.assertIsNone(result["source"])
        self.assertEqual(result["original_source"], entry["source"])
        self.assertFalse(result["followed"])
        with self.assertRaisesRegex(ValueError, "changed"):
            saved_lists.update_entries(
                entry, rows, dict(body, revision="stale", confirm_detach=True)
            )
        unchanged, _ = saved_lists.update_entries(
            entry, [dict(entry["items"][0], id="dup")], body
        )
        self.assertEqual(unchanged, entry)


class ListManagementHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(app, "DATA", Path(self.folder.name))
        self.data_patch.start()
        self.original = {
            "id": "target",
            "name": "Existing",
            "description": "Preserved",
            "source": None,
            "items": [
                {
                    "id": "old",
                    "type": "movie",
                    "tmdb": "1",
                    "title": "One",
                    "status": "available",
                    "plex_keys": ["kept"],
                }
            ],
        }
        self.state = {
            "settings": {"tmdb": {"key": "test"}},
            "lists": [copy.deepcopy(self.original)],
            "requests": [{"id": "history", "list_id": "target"}],
        }
        app.save_state(self.state)
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.data_patch.stop()
        self.folder.cleanup()

    def post(self, path, body):
        request = urllib.request.Request(
            "http://127.0.0.1:" + str(self.server.server_port) + "/api/" + path,
            data=json.dumps(body).encode(),
            headers={"Host": "127.0.0.1:8765", "X-Listweavarr-Token": app.SESSION},
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def assert_rejected(self, path, body):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(path, body)
        error.exception.close()

    def test_delete_requires_current_confirmation_keeps_external_history(self):
        body = {"list_id": "target", "revision": saved_lists.revision(self.original)}
        self.assert_rejected("lists/delete", body)
        self.assert_rejected("lists/delete", dict(body, confirmed=True, revision="old"))
        with (
            patch.object(app, "remote") as remote,
            patch.object(app, "request_item") as acquire,
        ):
            self.assertEqual(
                self.post("lists/delete", dict(body, confirmed=True))["deleted_id"],
                "target",
            )
            remote.assert_not_called()
            acquire.assert_not_called()
        state = app.read_state()
        self.assertEqual(state["lists"], [])
        self.assertEqual(state["requests"], self.state["requests"])

    def test_append_api_updates_in_place_and_retains_matching_availability(self):
        def metadata(path, settings):
            return {
                "id": int(path.rsplit("/", 1)[-1]),
                "title": "Verified movie",
                "release_date": "2000-01-01",
            }

        body = {
            "list_id": "target",
            "mode": "append",
            "revision": saved_lists.revision(self.original),
            "items": [
                {"confirmed": True, "type": "movie", "tmdb": "1"},
                {"confirmed": True, "type": "movie", "tmdb": "2"},
            ],
        }
        with (
            patch("providers.cached_tmdb", side_effect=metadata),
            patch.object(app, "request_item") as acquire,
        ):
            result = self.post("lists/build/save", body)
            acquire.assert_not_called()
        entry = result["entry"]
        self.assertEqual(entry["id"], "target")
        self.assertEqual(entry["name"], "Existing")
        self.assertEqual(len(app.read_state()["lists"]), 1)
        self.assertEqual(entry["items"][0], self.original["items"][0])
        self.assertEqual(result["update_report"]["skipped"], 1)
        self.assertEqual(result["update_report"]["added"], 1)
        self.assertEqual(entry["items"][1]["status"], "unchecked")
        self.assert_rejected("lists/build/save", body)

    def test_removing_target_during_metadata_lookup_does_not_recreate_it(self):
        def metadata(path, settings):
            with app.LOCK:
                state = app.read_state()
                state["lists"] = []
                app.save_state(state)
            return {"id": 2, "title": "New"}

        body = {
            "list_id": "target",
            "mode": "append",
            "revision": saved_lists.revision(self.original),
            "items": [{"confirmed": True, "type": "movie", "tmdb": "2"}],
        }
        with patch("providers.cached_tmdb", side_effect=metadata):
            self.assert_rejected("lists/build/save", body)
        self.assertEqual(app.read_state()["lists"], [])

    def test_source_refresh_does_not_resurrect_deleted_list(self):
        entered = threading.Event()
        release = threading.Event()
        self.state["lists"][0]["source"] = "https://example.com/list"
        app.save_state(self.state)

        def imported(*args):
            entered.set()
            release.wait(3)
            return {
                "name": "External",
                "source": "https://example.com/list",
                "items": [{"type": "movie", "title": "New", "tmdb": "2"}],
                "warnings": [],
            }

        with (
            patch.object(app.providers, "import_url", side_effect=imported),
            patch.object(
                app.providers, "enrich", side_effect=lambda row, settings: row
            ),
        ):
            job = app.start_import_job({"list_id": "target"})["job_id"]
            self.assertTrue(entered.wait(2))
            entry = app.read_state()["lists"][0]
            self.post(
                "lists/delete",
                {
                    "list_id": "target",
                    "revision": saved_lists.revision(entry),
                    "confirmed": True,
                },
            )
            release.set()
            deadline = time.time() + 3
            while time.time() < deadline:
                with app.JOBS_LOCK:
                    status = app.JOBS[job]["status"]
                if status != "running":
                    break
                time.sleep(0.01)
            self.assertEqual(status, "error")
            self.assertEqual(app.read_state()["lists"], [])


if __name__ == "__main__":
    unittest.main()
