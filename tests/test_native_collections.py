# SPDX-License-Identifier: AGPL-3.0-only
"""Native collection contracts use a disposable in-memory Plex, never real media."""
import copy
from pathlib import Path
import tempfile
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch
import app
import plex_collections as collections


def tree(tag, **attrs):
    return ET.Element(tag, {k: str(v) for k, v in attrs.items()})


class FakePlex:
    def __init__(self):
        self.keys = ["2", "1", "9"]
        self.calls = []
        self.exists = True
        self.title = "Owned"
        self.guid = "collection://owned"

    def remote(self, base, path, token, method="GET", **kwargs):
        self.calls.append((method, path))
        parsed = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        root = tree("MediaContainer")
        if path == "/":
            root.set("machineIdentifier", "machine")
        elif path == "/library/sections":
            root.append(tree("Directory", key="1", type="movie", title="Movies"))
        elif path == "/library/collections" and method == "POST":
            self.exists = True
            self.title = query["title"][0]
            self.keys = query["uri"][0].rsplit("/", 1)[1].split(",")
            root.append(tree("Directory", ratingKey="5", guid=self.guid))
        elif path == "/library/sections/1/collections":
            if self.exists:
                root.append(tree("Directory", ratingKey="5", title=self.title))
        elif path == "/library/collections/5":
            root.set("librarySectionID", "1")
            root.append(
                tree(
                    "Directory",
                    type="collection",
                    title=self.title,
                    guid=self.guid,
                    subtype="movie",
                    collectionSort="2",
                )
            )
        elif path == "/library/collections/5/children":
            root.set("totalSize", str(len(self.keys)))
            for key in self.keys:
                root.append(tree("Video", ratingKey=key))
        elif path == "/library/collections/5/items" and method == "PUT":
            self.keys += [
                k
                for k in query["uri"][0].rsplit("/", 1)[1].split(",")
                if k not in self.keys
            ]
        elif path.startswith("/library/collections/5/items/"):
            key = path.split("/")[5]
            if method == "DELETE":
                self.keys.remove(key)
            elif path.endswith("/move"):
                self.keys.remove(key)
                self.keys.insert(
                    self.keys.index(query["after"][0]) + 1 if query.get("after") else 0,
                    key,
                )
        elif path != "/library/metadata/5/prefs":
            raise AssertionError((method, path))
        return root


class NativeCollectionTests(unittest.TestCase):
    def test_unlink_is_local_only_and_works_with_unavailable_plex(self):
        target = self.saved()
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.DATA", Path(folder)
        ), patch("app.remote") as remote:
            app.save_state(
                {
                    "settings": {},
                    "lists": [
                        {
                            "id": "local",
                            "name": "List",
                            "items": [],
                            "plex_collection": target,
                        }
                    ],
                },
                backup=False,
            )
            with self.assertRaises(ValueError):
                app.collection_action(
                    "unlink", {"list_id": "local", "expected": target}
                )
            result = app.collection_action(
                "unlink", {"list_id": "local", "expected": target, "confirmed": True}
            )
            self.assertNotIn("plex_collection", result["entry"])
            remote.assert_not_called()

    def test_review_token_and_checkpoint_recovery_without_duplicate_creation(self):
        plex = FakePlex()
        plex.exists = False
        settings = self.settings()
        source = {
            "id": "local",
            "name": "New",
            "items": [{"id": "a", "type": "movie", "title": "Film", "tmdb": "1"}],
        }
        catalog = [
            {
                "key": "1",
                "type": "movie",
                "title": "Film",
                "ids": {"tmdb": "1"},
                "library_id": "1",
            }
        ]
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.DATA", Path(folder)
        ), patch("app.plex_catalog", return_value=catalog), patch(
            "app.remote", side_effect=plex.remote
        ):
            app.save_state({"settings": settings, "lists": [source]}, backup=False)
            preview = app.collection_action(
                "preview", {"list_id": "local", "section": "1", "title": "New"}
            )
            self.assertFalse(any(method != "GET" for method, path in plex.calls))
            with self.assertRaises(ValueError):
                app.collection_action(
                    "apply", {"list_id": "local", "token": preview["token"]}
                )
            self.assertFalse(any(method != "GET" for method, path in plex.calls))

            def interrupted(*args, **kwargs):
                if "/prefs?" in args[1] and kwargs.get("method") == "PUT":
                    raise ValueError("interrupted")
                return plex.remote(*args, **kwargs)

            with patch("app.remote", side_effect=interrupted), self.assertRaisesRegex(
                ValueError, "interrupted"
            ):
                app.collection_action(
                    "apply",
                    {"list_id": "local", "token": preview["token"], "confirmed": True},
                )
            saved = app.read_state()["lists"][0]
            self.assertEqual(saved["plex_collection"]["key"], "5")
            self.assertIn("collection_attention", saved)
            with self.assertRaises(ValueError):
                app.collection_action(
                    "apply",
                    {"list_id": "local", "token": preview["token"], "confirmed": True},
                )
            recovery = app.collection_action("preview", {"list_id": "local"})
            self.assertTrue(recovery["updating"])
            result = app.collection_action(
                "apply",
                {"list_id": "local", "token": recovery["token"], "confirmed": True},
            )
            self.assertNotIn("collection_attention", result["entry"])
            self.assertEqual(sum(method == "POST" for method, path in plex.calls), 1)

    def settings(self):
        return {"plex": {"url": "http://plex", "key": "private"}}

    def saved(self):
        return {
            "key": "5",
            "title": "Owned",
            "section": "1",
            "kind": "movie",
            "guid": "collection://owned",
            "machine": "machine",
            "server": "http://plex",
        }

    def test_plan_uses_one_library_and_unique_confirmed_identity(self):
        entry = {
            "items": [
                {"type": "movie", "title": "Film", "tmdb": "1"},
                {"type": "movie", "title": "Repeat", "tmdb": "1"},
                {"type": "movie", "title": "Absent", "tmdb": "2"},
            ]
        }
        catalog = [
            {
                "key": "10",
                "type": "movie",
                "title": "Film",
                "ids": {"tmdb": "1"},
                "library_id": "1",
            },
            {
                "key": "20",
                "type": "movie",
                "title": "Film",
                "ids": {"tmdb": "1"},
                "library_id": "2",
            },
        ]
        result = collections.plan(
            entry, catalog, {"id": "1", "type": "movie"}, app.match_item
        )
        self.assertEqual(result["keys"], ["10"])
        self.assertEqual((result["deduplicated"], result["omitted"]), (1, 1))
        with self.assertRaises(ValueError):
            collections.kind({"items": [{"type": "episode"}]})
        with self.assertRaises(ValueError):
            collections.kind({"items": [{"type": "movie"}, {"type": "show"}]})

    def test_update_preserves_identity_verifies_order_and_never_deletes_media(self):
        plex = FakePlex()
        saved = self.saved()
        before = collections.target(saved, self.settings(), plex.remote)
        proposal = {
            "target": before,
            "desired": {"keys": ["1", "2", "3"], "section": "1", "kind": "movie"},
            "title": "Owned",
        }
        checkpoint = Mock()
        upload = Mock()
        result = collections.apply(
            proposal,
            {"plex_collection": saved, "poster": "portrait"},
            self.settings(),
            plex.remote,
            Mock(),
            checkpoint,
            upload,
        )
        self.assertEqual(plex.keys, ["1", "2", "3"])
        self.assertEqual(result["key"], "5")
        self.assertEqual(
            [path for method, path in plex.calls if method == "DELETE"],
            ["/library/collections/5/items/9"],
        )
        self.assertFalse(any(method == "POST" for method, path in plex.calls))
        checkpoint.assert_called_once()
        upload.assert_called_once_with("5", "portrait", self.settings()["plex"])

    def test_remote_drift_and_guid_changes_block_all_writes(self):
        plex = FakePlex()
        saved = self.saved()
        before = collections.target(saved, self.settings(), plex.remote)
        plex.keys.append("8")
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            collections.apply(
                {"target": before, "desired": {"keys": ["1"]}},
                {"plex_collection": saved},
                self.settings(),
                plex.remote,
                Mock(),
                Mock(),
                Mock(),
            )
        self.assertFalse(any(method != "GET" for method, path in plex.calls))
        plex.guid = "collection://someone-else"
        with self.assertRaisesRegex(ValueError, "replaced"):
            collections.target(saved, self.settings(), plex.remote)

    def test_create_refuses_name_collision_and_checkpoints_new_identity(self):
        plex = FakePlex()
        with self.assertRaisesRegex(ValueError, "already exists"):
            collections.name_available(
                "Owned", "1", self.settings()["plex"], plex.remote
            )
        plex.exists = False
        checkpoint = Mock()
        result = collections.apply(
            {
                "target": None,
                "title": "New",
                "desired": {"keys": ["3", "1"], "section": "1", "kind": "movie"},
            },
            {},
            self.settings(),
            plex.remote,
            Mock(),
            checkpoint,
            Mock(),
        )
        self.assertEqual(result["keys"], ["3", "1"])
        self.assertEqual(checkpoint.call_args.args[0]["guid"], "collection://owned")

    def test_unknown_manual_override_from_another_server_is_not_used(self):
        catalog = [
            {
                "key": "10",
                "type": "movie",
                "title": "Different",
                "ids": {"tmdb": "9"},
                "library_id": "1",
            }
        ]
        row = {
            "type": "movie",
            "title": "Film",
            "tmdb": "1",
            "plex_override": "10",
            "plex_server": "http://other",
        }
        result = collections.plan(
            {"items": [row]},
            catalog,
            {"id": "1", "type": "movie"},
            app.match_item,
            "http://plex",
        )
        self.assertEqual(result["keys"], [])
