# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import app
import official_lists
from scripts import publish_catalogue


class OfficialCatalogueTests(unittest.TestCase):
    def test_publishing_only_includes_portable_fields_and_versions_changes(self):
        state = {
            "settings": {"secret": "never export"},
            "lists": [
                {
                    "id": "one",
                    "name": "Example",
                    "description": "Description",
                    "poster": "",
                    "items": [
                        {
                            "id": "private-id",
                            "type": "movie",
                            "title": "Film",
                            "tmdb": "1",
                            "status": "available",
                            "plex_keys": ["private"],
                            "request_log": "private",
                        }
                    ],
                }
            ],
        }
        data = publish_catalogue.publish(state, {"version": 0, "lists": []})
        text = str(data)
        for value in (
            "never export",
            "private-id",
            "plex_keys",
            "request_log",
            "available",
        ):
            self.assertNotIn(value, text)
        self.assertEqual(data["lists"][0]["version"], 1)
        state["lists"][0]["official_id"] = data["lists"][0]["id"]
        self.assertEqual(publish_catalogue.publish(state, data), data)
        state["lists"][0]["description"] = "Changed"
        updated = publish_catalogue.publish(state, data)
        self.assertEqual(updated["lists"][0]["version"], 2)
        self.assertEqual(updated["version"], 2)

    def test_personal_copy_has_new_ids_and_no_authoring_flag(self):
        row = {
            "id": "official-example",
            "version": 3,
            "name": "Example",
            "description": "",
            "poster": "",
            "items": [
                {
                    "type": "season",
                    "title": "Season 1",
                    "show_title": "Show",
                    "show_tmdb": "9",
                    "season": "1",
                }
            ],
        }
        with patch.object(official_lists, "get", return_value=row):
            first = official_lists.instantiate("official-example", app.normalize)
            second = official_lists.instantiate("official-example", app.normalize)
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertEqual(first["official_version"], 3)
        self.assertEqual(first["items"][0]["status"], "unchecked")
        self.assertNotIn("official_authoring", first)

    def test_bundled_catalogue_has_no_private_state(self):
        document = official_lists.document()
        self.assertGreaterEqual(len(document["lists"]), 25)
        for entry in document["lists"]:
            self.assertNotIn("source", entry)
            for item in entry["items"]:
                self.assertNotIn("status", item)
                self.assertNotIn("plex_keys", item)

    def test_single_publication_preserves_other_lists_and_is_idempotent(self):
        previous = {
            "version": 4,
            "lists": [{"id": "existing", "version": 2, "name": "Other", "items": []}],
        }
        original = {
            "id": "new",
            "name": "Dragon Ball",
            "items": [
                {
                    "id": "personal",
                    "type": "movie",
                    "title": "Film",
                    "tmdb": "1",
                    "status": "available",
                    "plex_keys": ["secret"],
                }
            ],
            "request_history": ["private"],
        }
        document, working, report = official_lists.prepare_publish(
            original, previous, app.normalize
        )
        self.assertEqual(document["lists"][0], previous["lists"][0])
        self.assertEqual(len(document["lists"]), 2)
        self.assertTrue(working["official_authoring"])
        self.assertEqual(working["items"], original["items"])
        self.assertNotIn("official_id", original)
        self.assertNotIn("secret", str(document))
        self.assertNotIn("request_history", str(document))
        again, _, report = official_lists.prepare_publish(
            working, document, app.normalize
        )
        self.assertEqual(again, document)
        self.assertFalse(report["changed"])
        working["description"] = "Updated"
        changed, _, report = official_lists.prepare_publish(
            working, document, app.normalize
        )
        self.assertEqual(changed["lists"][-1]["version"], 2)
        self.assertEqual(len(changed["lists"]), 2)
