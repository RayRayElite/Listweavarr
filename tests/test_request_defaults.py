# SPDX-License-Identifier: AGPL-3.0-only
import json
import unittest
from unittest.mock import patch

import app


class RequestDefaultsTests(unittest.TestCase):
    def test_defaults_survive_serialization_and_stay_separate_by_service(self):
        state = {
            "settings": {
                "radarr": {"url": "http://movies"},
                "sonarr": {"url": "http://tv"},
            }
        }
        app.remember_request_options(state, "radarr", 2, "/movies")
        app.remember_request_options(state, "sonarr", 7, "/series")
        restored = json.loads(json.dumps(state))
        with patch(
            "app.arr_call", side_effect=[[{"id": 1}, {"id": 2}], [{"path": "/movies"}]]
        ):
            options = app.request_options(restored, "radarr")
        self.assertEqual(options["defaults"], {"profile": "2", "root": "/movies"})
        self.assertEqual(restored["request_defaults"]["sonarr"]["profile"], "7")

    def test_removed_profile_and_destination_are_not_preselected(self):
        state = {"settings": {"radarr": {"url": "http://movies"}}}
        app.remember_request_options(state, "radarr", 2, "/removed")
        with patch("app.arr_call", side_effect=[[{"id": 1}], [{"path": "/new"}]]):
            self.assertEqual(app.request_options(state, "radarr")["defaults"], {})

    def test_another_server_does_not_inherit_defaults(self):
        state = {"settings": {"sonarr": {"url": "http://old"}}}
        app.remember_request_options(state, "sonarr", 7, "/tv")
        state["settings"]["sonarr"]["url"] = "http://new"
        with patch("app.arr_call", side_effect=[[{"id": 7}], [{"path": "/tv"}]]):
            self.assertEqual(app.request_options(state, "sonarr")["defaults"], {})
