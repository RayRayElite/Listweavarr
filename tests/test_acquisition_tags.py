# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
from unittest.mock import patch
import acquisition_tags
import app
import request_ledger


class AcquisitionTagTests(unittest.TestCase):
    def test_values_are_explicit_existing_and_additive(self):
        choices = [{"id": 1}, {"id": 2}]
        self.assertEqual(acquisition_tags.validate(["2", 2], choices), [2])
        for value in ([9], "2", [True], [-1], [1.2]):
            with self.assertRaises(ValueError):
                acquisition_tags.validate(value, choices)
        record = {"tags": [9, 1]}
        self.assertTrue(acquisition_tags.apply(record, [2]))
        self.assertEqual(record["tags"], [9, 1, 2])
        self.assertFalse(acquisition_tags.apply(record, [2]))

    def test_request_adds_only_reviewed_tags_to_an_existing_movie(self):
        movie = {"id": 7, "tmdbId": 1, "hasFile": False, "tags": [9]}
        writes = []

        def call(settings, service, path, payload=None, method=None):
            if payload is not None:
                writes.append((path, copy.deepcopy(payload), method))
                return payload
            return {
                "qualityprofile": [{"id": 1}],
                "rootfolder": [{"path": "/movies"}],
                "tag": [{"id": 2, "label": "Curated"}],
                "movie": [movie],
            }[path]

        with patch("app.arr_call", side_effect=call):
            app.request_item(
                {"type": "movie", "tmdb": "1", "title": "Film"},
                {"_request_tags": [2]},
                1,
                "/movies",
            )
        self.assertEqual(writes[0][0], "movie/7")
        self.assertEqual(writes[0][1]["tags"], [9, 2])
        self.assertEqual(writes[0][2], "PUT")
        self.assertEqual(writes[1][0], "command")

    def test_removed_tag_blocks_all_manager_writes(self):
        calls = []

        def call(settings, service, path, payload=None, method=None):
            calls.append((path, payload))
            return {
                "qualityprofile": [{"id": 1}],
                "rootfolder": [{"path": "/movies"}],
                "tag": [],
            }[path]

        with patch("app.arr_call", side_effect=call), self.assertRaises(ValueError):
            app.request_item(
                {"type": "movie", "tmdb": "1", "title": "Film"},
                {"_request_tags": [2]},
                1,
                "/movies",
            )
        self.assertTrue(all(payload is None for path, payload in calls))

    def test_saved_list_tags_are_scoped_to_the_route_and_removed_ones_warn(self):
        state = {
            "settings": {"radarr": {"url": "http://fixture", "key": "fixture"}},
            "lists": [
                {
                    "id": "list",
                    "request_preferences": {
                        "radarr": {
                            "route": "primary",
                            "server": "http://fixture",
                            "profile": "1",
                            "root": "/movies",
                            "tags": [2, 3],
                        }
                    },
                }
            ],
        }
        with patch(
            "app.arr_call",
            side_effect=[
                [{"id": 1}],
                [{"path": "/movies"}],
                [{"id": 2, "label": "Curated"}],
            ],
        ):
            options = app.request_options(
                state, "radarr", list_id="list", include_tags=True
            )
        self.assertEqual(options["defaults"]["tags"], [2])
        self.assertTrue(options["warning"])
        saved = request_ledger.record(
            {},
            {"type": "movie", "title": "Film", "tmdb": "1"},
            options={"profile": 1, "root": "/movies", "tags": [2]},
        )
        self.assertEqual(saved["options"]["tags"], [2])
