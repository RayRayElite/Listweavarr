# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
import saved_lists


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.target = {
            "id": "a",
            "name": "Target",
            "items": [
                {
                    "id": "old",
                    "title": "Owned",
                    "type": "movie",
                    "tmdb": "1",
                    "status": "available",
                }
            ],
            "playlist": {"id": "p"},
            "poster": "",
        }
        self.sources = [
            {
                "id": "b",
                "items": [
                    {
                        "id": "s1",
                        "title": "First",
                        "type": "episode",
                        "show_tmdb": "2",
                        "season": 1,
                        "episode": 1,
                        "plex_keys": ["private"],
                        "status": "available",
                    },
                    {
                        "id": "s2",
                        "title": "Second",
                        "type": "episode",
                        "show_tmdb": "2",
                        "season": 1,
                        "episode": 2,
                    },
                ],
            },
            {
                "id": "c",
                "items": [{"id": "s3", "title": "Third", "type": "movie", "tmdb": "3"}],
            },
        ]

    def test_append_preserves_order_and_resets_availability_without_mutating_sources(
        self,
    ):
        before = copy.deepcopy(self.sources)
        result, report = saved_lists.append_lists(
            self.target, self.sources, {"revision": saved_lists.revision(self.target)}
        )
        self.assertEqual(
            [r["title"] for r in result["items"]], ["Owned", "First", "Second", "Third"]
        )
        self.assertEqual(report["added"], 3)
        self.assertEqual(len({r["id"] for r in result["items"]}), 4)
        self.assertNotIn("plex_keys", result["items"][1])
        self.assertEqual(result["items"][1]["status"], "unchecked")
        self.assertTrue(result["playlist_needs_update"])
        self.assertEqual(self.sources, before)
        self.assertEqual(len(self.target["items"]), 1)

    def test_duplicates_explicit_choice_and_source_detachment(self):
        sources = [{"id": "b", "items": self.target["items"]}]
        body = {"revision": saved_lists.revision(self.target)}
        self.assertEqual(
            saved_lists.append_lists(self.target, sources, body)[1]["added"], 0
        )
        self.assertEqual(
            saved_lists.append_lists(
                self.target, sources, dict(body, skip_duplicates=False)
            )[1]["added"],
            1,
        )
        self.target["source"] = {"url": "https://example.org"}
        body["revision"] = saved_lists.revision(self.target)
        with self.assertRaises(ValueError):
            saved_lists.append_lists(self.target, self.sources, body)
        result, _ = saved_lists.append_lists(
            self.target, self.sources, dict(body, confirm_detach=True)
        )
        self.assertIsNone(result["source"])

    def test_remove_revision_validation_link_protection_and_playlist_update(self):
        body = {"revision": saved_lists.revision(self.target), "ids": ["old"]}
        result = saved_lists.remove_entries(self.target, body, lambda row: row)
        self.assertEqual(result["items"], [])
        self.assertTrue(result["playlist_needs_update"])
        with self.assertRaises(ValueError):
            saved_lists.remove_entries(
                self.target, dict(body, revision="stale"), lambda row: row
            )
        with self.assertRaises(ValueError):
            saved_lists.remove_entries(
                self.target, dict(body, ids=["gone"]), lambda row: row
            )
        self.target["source"] = {"url": "https://example.org"}
        with self.assertRaises(ValueError):
            saved_lists.remove_entries(
                self.target,
                dict(body, revision=saved_lists.revision(self.target)),
                lambda row: row,
            )


class MembershipApiTests(unittest.TestCase):
    def test_routes_review_sources_and_preserve_order(self):
        import json
        import tempfile
        import threading
        import urllib.request
        import urllib.error
        from pathlib import Path
        from unittest.mock import patch
        import app

        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            app.save_state(
                {
                    "settings": {},
                    "lists": [
                        {"id": "a", "name": "Target", "items": []},
                        {
                            "id": "b",
                            "name": "Source",
                            "items": [
                                {
                                    "id": "one",
                                    "type": "movie",
                                    "title": "One",
                                    "tmdb": "1",
                                }
                            ],
                        },
                    ],
                }
            )
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()

            def post(path, body):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/" + path,
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    return json.load(response)

            try:
                options = post("lists/append-options", {"list_id": "a"})["sources"]
                self.assertEqual(
                    options[0]["entry"], {"id": "b", "name": "Source", "count": 1}
                )
                revision = post("lists/revision", {"list_id": "a"})["revision"]
                body = {
                    "list_id": "a",
                    "revision": revision,
                    "source_ids": ["b"],
                    "source_revisions": {"b": "stale"},
                }
                with self.assertRaises(urllib.error.HTTPError):
                    post("lists/append-lists", body)
                self.assertEqual(app.read_state()["lists"][0]["items"], [])
                body["source_revisions"]["b"] = options[0]["revision"]
                added = post("lists/append-lists", body)["entry"]
                self.assertEqual(added["items"][0]["title"], "One")
                removed = post(
                    "lists/remove-entries",
                    {
                        "list_id": "a",
                        "revision": saved_lists.revision(added),
                        "ids": [added["items"][0]["id"]],
                    },
                )["entry"]
                self.assertEqual(removed["items"], [])
                self.assertEqual(len(app.read_state()["lists"][1]["items"]), 1)
            finally:
                server.shutdown()
                server.server_close()
