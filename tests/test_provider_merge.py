# SPDX-License-Identifier: AGPL-3.0-only
"""Provider merges are drafts, not imports that overwrite a saved collection."""
import json
import threading
import unittest
import urllib.request
from unittest.mock import patch

import app
import saved_lists


class ProviderMergeTests(unittest.TestCase):
    def test_preview_reads_supported_adapter_without_saving(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        result = {
            "name": "Incoming",
            "source": "https://trakt.tv/users/example/lists/order",
            "items": [
                {
                    "type": "episode",
                    "title": "Pilot",
                    "show_tvdb": "42",
                    "season": 1,
                    "episode": 2,
                }
            ],
            "warnings": ["Review scope"],
        }
        try:
            with patch("app.read_state", return_value={"settings": {}}), patch(
                "app.providers.import_url", return_value=result
            ) as imported, patch("app.save_state") as save:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/lists/provider-preview",
                    data=json.dumps({"url": result["source"]}).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    preview = json.load(response)
                self.assertEqual(preview["items"][0]["show_tvdb"], "42")
                self.assertEqual(preview["warnings"], ["Review scope"])
                imported.assert_called_once()
                save.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()

    def test_editor_keeps_scope_ids_and_requires_link_detachment(self):
        original = {
            "id": "list",
            "name": "Original",
            "source": "https://trakt.tv/users/example/lists/order",
            "items": [],
        }
        body = {
            "name": "Merged",
            "revision": saved_lists.revision(original),
            "items": [
                {
                    "type": "episode",
                    "title": "Pilot",
                    "show_tvdb": "42",
                    "show_imdb": "tt123",
                    "season": 1,
                    "episode": 2,
                    "metadata_unresolved": True,
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "Confirm converting"):
            saved_lists.edit(original, body, app.normalize)
        result = saved_lists.edit(
            original, {**body, "confirm_detach": True}, app.normalize
        )
        self.assertIsNone(result["source"])
        self.assertEqual(result["items"][0]["show_tvdb"], "42")
        self.assertEqual(result["items"][0]["show_imdb"], "tt123")
        self.assertTrue(result["items"][0]["metadata_unresolved"])
