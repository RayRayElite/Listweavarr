# SPDX-License-Identifier: AGPL-3.0-only
"""Source checks preserve lists, handle duplicate occurrences and reject stale results."""
import copy
import json
import threading
import unittest
import urllib.request
from unittest.mock import patch

import app
import list_updates


def entry():
    return {
        "id": "list",
        "name": "Example",
        "source": "https://trakt.tv/users/test/lists/example",
        "items": [{"id": "one", "type": "movie", "title": "First", "tmdb": "1"}],
        "update_schedule": {"interval": "daily", "next_run": 0},
    }


class ListUpdateTests(unittest.TestCase):
    def test_apply_exact_snapshot_preserves_ids_paths_and_runtime_then_undo(self):
        row = entry()
        row["playlist"] = {"key": "77", "server": "http://plex", "title": "Example"}
        first = row["items"][0]
        first["status"] = "available"
        row["items"].append(
            {"id": "remove", "type": "movie", "title": "Removed", "tmdb": "3"}
        )
        row["watch_paths"] = {"essential": ["one", "remove"]}
        original = copy.deepcopy(row["items"])
        incoming = [{"type": "movie", "title": "New", "tmdb": "2"}, first]
        list_updates.stage(row, incoming, "provider-v2", 1)
        token = row["update_pending"]["token"]
        proposed = list_updates.preview(row, token)
        self.assertIsNone(proposed["items"][0]["previous_position"])
        self.assertEqual(proposed["items"][1]["previous_position"], 1)
        incoming[0]["title"] = "Changed elsewhere"
        list_updates.apply(row, token, 2, app.normalize)
        self.assertEqual(row["playlist"]["key"], "77")
        self.assertTrue(row["playlist_needs_update"])
        row["playlist_needs_update"] = False
        self.assertEqual(row["items"][0]["title"], "New")
        self.assertEqual(row["items"][1]["id"], "one")
        self.assertEqual(row["watch_paths"]["essential"], ["one"])
        row["description"] = "Keep my description"
        row["items"][1]["status"] = "fresh-runtime-status"
        list_updates.undo(row, row["source_update_undo"]["token"], 3)
        self.assertTrue(row["playlist_needs_update"])
        self.assertEqual([x["id"] for x in row["items"]], ["one", "remove"])
        self.assertEqual(row["items"][0]["status"], "fresh-runtime-status")
        self.assertEqual(row["description"], "Keep my description")
        self.assertEqual(row["watch_paths"]["essential"], ["one", "remove"])
        self.assertNotIn("source_version", row)
        self.assertNotIn("source_update_undo", row)

    def test_stale_tokens_and_intervening_edits_rejected(self):
        row = entry()
        list_updates.stage(row, [], None, 1)
        with self.assertRaises(ValueError):
            list_updates.apply(row, "wrong", 2, app.normalize)
        token = row["update_pending"]["token"]
        row["items"][0]["title"] = "User correction"
        with self.assertRaises(ValueError):
            list_updates.apply(row, token, 2, app.normalize)
        list_updates.stage(row, [], None, 3)
        list_updates.apply(row, row["update_pending"]["token"], 4, app.normalize)
        token = row["source_update_undo"]["token"]
        row["source"] = "https://trakt.tv/users/other/lists/different"
        with self.assertRaises(ValueError):
            list_updates.undo(row, token, 5)

    def test_failed_recheck_invalidates_pending_snapshot(self):
        row = entry()
        list_updates.stage(row, [], None, 1)
        list_updates.finish(row, 2)
        self.assertNotIn("update_pending", row)

    def test_occurrences_and_reorder(self):
        a = entry()["items"][0]
        b = {**a, "tmdb": "2"}
        self.assertFalse(list_updates.summarize([a, a, b], [a, a, b])["changed"])
        result = list_updates.summarize([a, a, b], [b, a])
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["added"], 0)
        self.assertTrue(result["reordered"])

    def test_opt_in_pause_and_retry(self):
        row = entry()
        state = {"lists": [row]}
        self.assertIs(list_updates.due(state, 10), row)
        state["list_update_scheduler"] = {"paused": True}
        self.assertIsNone(list_updates.due(state, 10))
        list_updates.finish(row, 10)
        self.assertEqual(row["update_schedule"]["next_run"], 910)
        list_updates.finish(row, 20)
        self.assertEqual(row["update_schedule"]["next_run"], 1820)
        list_updates.finish(row, 30, {"changed": False})
        self.assertEqual(row["update_schedule"]["failures"], 0)
        self.assertEqual(row["update_schedule"]["last_success"], 30)
        row["update_schedule"]["interval"] = "off"
        state["list_update_scheduler"]["paused"] = False
        self.assertIsNone(list_updates.due(state, 999999))
        row.pop("update_schedule")
        self.assertIsNone(list_updates.due(state, 999999))

    def test_partial_sources_are_not_reported_as_removals(self):
        state = {"lists": [entry()], "settings": {}}
        with patch("app.read_state", side_effect=lambda: copy.deepcopy(state)), patch(
            "app.save_state", side_effect=lambda value: state.update(value)
        ), patch(
            "app.providers.import_url",
            return_value={"items": [], "warnings": ["Partial response"]},
        ):
            with self.assertRaises(ValueError):
                app.check_linked_list("list")
        self.assertNotIn("update_review", state["lists"][0])
        self.assertIn("incomplete", state["lists"][0]["update_schedule"]["last_error"])

    def test_checks_do_not_mutate_content_or_write_to_services(self):
        row = entry()
        state = {"lists": [row], "settings": {}}
        before = copy.deepcopy(row["items"])
        with patch("app.read_state", side_effect=lambda: copy.deepcopy(state)), patch(
            "app.save_state", side_effect=lambda value: state.update(value)
        ), patch(
            "app.providers.import_url",
            return_value={
                "items": before + [{"type": "movie", "title": "Second", "tmdb": "2"}]
            },
        ), patch(
            "app.providers.enrich", side_effect=lambda value, settings: value
        ), patch(
            "app.remote"
        ) as remote, patch(
            "app.arr_call"
        ) as arr:
            app.check_linked_list("list")
        self.assertEqual(state["lists"][0]["items"], before)
        self.assertEqual(state["lists"][0]["update_review"]["added"], 1)
        remote.assert_not_called()
        arr.assert_not_called()

    def test_stale_source_result_and_secret_failure(self):
        state = {"lists": [entry()], "settings": {}}
        changed = copy.deepcopy(state)
        changed["lists"][0]["items"] = []
        with patch("app.read_state", side_effect=[state, changed]), patch(
            "app.save_state"
        ) as save, patch("app.providers.import_url", return_value={"items": []}):
            app.check_linked_list("list")
        save.assert_not_called()
        with patch("app.read_state", side_effect=lambda: copy.deepcopy(state)), patch(
            "app.save_state", side_effect=lambda value: state.update(value)
        ), patch(
            "app.providers.import_url", side_effect=ValueError("secret-api-token")
        ):
            with self.assertRaisesRegex(ValueError, "Source check failed"):
                app.check_linked_list("list")
        self.assertNotIn("secret-api-token", json.dumps(state))
        self.assertIsNone(app.LIST_UPDATE_RUNNING)

    def test_csv_export_http_route(self):
        # Exercises routing, not just the serializer: CSV must reach the list
        # export handler rather than accidentally matching backup export.
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/list-updates.js",
                    headers={"Host": "127.0.0.1:8765"},
                )
            ) as response:
                self.assertIn("renderLinkedUpdates", response.read().decode())
            with patch("app.read_state", return_value={"lists": [entry()]}):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/lists/share/csv",
                    data=json.dumps({"list_id": "list"}).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(req) as response:
                    self.assertIn("First", json.load(response)["csv"])
        finally:
            server.shutdown()
            server.server_close()

    def test_http_review_apply_undo_without_provider_fetch(self):
        state = {"lists": [entry()], "settings": {}}
        row = state["lists"][0]
        list_updates.stage(row, [], "new-version", 1)
        token = row["update_pending"]["token"]
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def post(action, token):
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/list-updates/{action}",
                data=json.dumps({"list_id": "list", "token": token}).encode(),
                headers={"Host": "127.0.0.1:8765", "X-Listweavarr-Token": app.SESSION},
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        try:
            with patch("app.read_state", return_value=state), patch(
                "app.save_state"
            ) as save, patch("app.providers.import_url") as fetch:
                self.assertEqual(post("preview", token)["items"], [])
                self.assertFalse(save.called)
                result = post("apply", token)
                self.assertEqual(result["workspace"]["lists"][0]["items"], [])
                result = post("undo", result["lists"][0]["undo_token"])
                self.assertEqual(
                    result["workspace"]["lists"][0]["items"][0]["id"], "one"
                )
                fetch.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
