# SPDX-License-Identifier: AGPL-3.0-only
"""List-specific defaults remain local and never bypass request review."""
import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import app
import saved_lists
import list_sharing


def fixture():
    return {
        "settings": {"radarr": {"url": "http://movies", "key": "fixture"}},
        "lists": [
            {
                "id": "one",
                "name": "One",
                "items": [],
                "source": {"url": "https://example.com/list"},
                "request_preferences": {
                    "radarr": {
                        "route": "primary",
                        "server": "http://movies",
                        "profile": "2",
                        "root": "/curated",
                    }
                },
            },
            {"id": "two", "name": "Two", "items": []},
        ],
    }


def manager(settings, service, path, *args, **kwargs):
    if args or kwargs:
        raise AssertionError("Preferences must not write to a manager")
    return (
        [{"id": 1}, {"id": 2}]
        if path == "qualityprofile"
        else [{"path": "/normal"}, {"path": "/curated"}]
    )


class ListAcquisitionTests(unittest.TestCase):
    def test_list_isolation_and_portable_export(self):
        state = fixture()
        with patch("app.arr_call", side_effect=manager):
            self.assertEqual(
                app.request_options(state, "radarr", list_id="one")["defaults"],
                {"profile": "2", "root": "/curated"},
            )
            self.assertEqual(
                app.request_options(state, "radarr", list_id="two")["defaults"], {}
            )
            self.assertEqual(app.request_options(state, "radarr")["defaults"], {})
        self.assertNotIn("request_preferences", list_sharing.export(state["lists"][0]))

    def test_removed_values_and_changed_server_warn_without_using_stale_options(self):
        state = fixture()
        with patch("app.arr_call", side_effect=[[{"id": 1}], [{"path": "/normal"}]]):
            result = app.request_options(state, "radarr", list_id="one")
        self.assertTrue(result["warning"])
        self.assertEqual(result["defaults"], {})
        state["settings"]["radarr"]["url"] = "http://changed"
        with patch("app.arr_call", side_effect=manager):
            result = app.request_options(state, "radarr", list_id="one")
        self.assertTrue(result["warning"])
        self.assertEqual(result["defaults"], {})

    def test_explicit_route_wins_and_disabled_list_route_falls_back(self):
        state = fixture()
        state["manager_instances"] = [
            {
                "id": "other",
                "service": "radarr",
                "name": "Other",
                "tier": "4k",
                "enabled": True,
                "url": "http://other",
                "key": "fixture",
            }
        ]
        state["lists"][0]["request_preferences"]["radarr"].update(
            route="other", server="http://other"
        )
        with patch("app.arr_call", side_effect=manager):
            self.assertEqual(
                app.request_options(state, "radarr", list_id="one")["route"], "other"
            )
            self.assertEqual(
                app.request_options(state, "radarr", "primary", "one")["route"],
                "primary",
            )
            state["manager_instances"][0]["enabled"] = False
            self.assertTrue(
                app.request_options(state, "radarr", list_id="one")["warning"]
            )

    def test_http_save_validates_revision_options_and_configuration_reset_works_offline(
        self,
    ):
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            app.save_state(fixture())
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()

            def post(action, body):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/lists/acquisition/{action}",
                    data=json.dumps({"list_id": "one", **body}).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    return json.load(response)

            try:
                with patch("app.arr_call", side_effect=manager):
                    options = post("options", {"service": "radarr"})
                    body = {
                        "service": "radarr",
                        "route": options["route"],
                        "revision": options["revision"],
                        "signature": options["signature"],
                        "profile": "1",
                        "root": "/normal",
                    }
                    with self.assertRaises(urllib.error.HTTPError):
                        post("save", {**body, "root": "/removed"})
                    post("save", body)
                    with self.assertRaises(urllib.error.HTTPError):
                        post("save", body)
                    new = post("options", {"service": "radarr"})
                    changed = app.read_state()
                    changed["settings"]["radarr"]["url"] = "http://changed"
                    app.save_state(changed)
                    with self.assertRaises(urllib.error.HTTPError):
                        post(
                            "save",
                            {
                                **body,
                                "revision": new["revision"],
                                "signature": new["signature"],
                            },
                        )
                with patch(
                    "app.arr_call",
                    side_effect=AssertionError(
                        "offline reset must not contact manager"
                    ),
                ):
                    revision = post("options", {})["revision"]
                    post("reset", {"revision": revision})
                saved = app.read_state()
                self.assertNotIn("request_preferences", saved["lists"][0])
                self.assertEqual(
                    saved["lists"][0]["source"], fixture()["lists"][0]["source"]
                )
            finally:
                server.shutdown()
                server.server_close()
