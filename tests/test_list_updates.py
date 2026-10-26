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
