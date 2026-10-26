# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
from urllib.parse import urlsplit
import unittest
from unittest.mock import patch
import app
import catalogue_feed as feed


def row(identifier="one", version=1, title="Film"):
    return {
        "id": identifier,
        "version": version,
        "name": "Collection " + identifier,
        "description": "",
        "poster": "",
        "items": [{"type": "movie", "title": title, "tmdb": "1"}],
    }


def document(rows=None):
    return {
        "format": "reelcheck-official-catalogue",
        "version": 1,
        "lists": rows or [row()],
    }


class CatalogueFeedTests(unittest.TestCase):
    def test_sanitizes_runtime_fields_and_keeps_paths(self):
        raw = document()
        raw["lists"][0]["secret"] = "never export"
        raw["lists"][0]["items"][0]["plex_keys"] = ["private"]
        raw["lists"][0]["paths"] = {"essential": [0]}
        cleaned = feed.validate(raw, app.normalize)
        self.assertNotIn("secret", cleaned["lists"][0])
        self.assertNotIn("plex_keys", cleaned["lists"][0]["items"][0])
        self.assertEqual(cleaned["lists"][0]["paths"], {"essential": [0]})

    def test_bad_formats_duplicate_ids_and_versions_rejected(self):
        bad = [{"lists": []}, document([row(), row()]), document([row(version=0)])]
        for value in bad:
            with self.assertRaises(ValueError):
                feed.validate(value, app.normalize)

    def test_merge_keeps_local_omissions_and_skips_older(self):
        current = document([row("one", 2), row("local", 1)])
        incoming = document([row("one", 1), row("new", 1)])
        merged, summary = feed.merge(current, incoming)
        self.assertEqual([r["id"] for r in merged["lists"]], ["one", "local", "new"])
        self.assertEqual(summary["older"], ["Collection one"])
        self.assertEqual(summary["kept_local"], 1)
        self.assertEqual(current["version"], 1)

    def test_same_version_changed_content_rejected(self):
        with self.assertRaisesRegex(ValueError, "without a new version"):
            feed.merge(document(), document([row(title="Changed")]))

    def test_review_requires_current_catalogue_and_expires(self):
        current = document()
        preview = feed.stage(current, document([row(version=2)]))
        self.assertEqual(
            feed.reviewed(preview["token"], current)["document"]["lists"][0]["version"],
            2,
        )
        different = copy.deepcopy(current)
        different["version"] = 3
        with self.assertRaisesRegex(ValueError, "changed"):
            feed.reviewed(preview["token"], different)
        with patch("catalogue_feed.time.time", return_value=10**12):
            with self.assertRaisesRegex(ValueError, "expired"):
                feed.reviewed(preview["token"], current)

    def test_source_credentials_and_non_https_rejected(self):
        for value in (
            "http://example.com/file.json",
            "https://user:pass@example.com/file.json",
            "https://example.com/file.json?token=secret",
            "https://example.com:8443/file.json",
        ):
            with self.assertRaises(ValueError):
                feed.source_url(value)
        self.assertEqual(
            feed.source_url("https://example.com/file.json?raw=1"),
            "https://example.com/file.json?raw=1",
        )

    def test_private_target_rejected_before_connection(self):
        with (
            patch(
                "text_list_builder.public_target",
                side_effect=ValueError("private address"),
            ),
            patch("catalogue_feed.socket.create_connection") as connect,
        ):
            with self.assertRaises(ValueError):
                feed.download("https://example.com/list.json")
        connect.assert_not_called()

    def test_download_accepts_json_and_revalidates_redirect_targets(self):
        class Response:
            def __init__(self, status, headers, data=b""):
                self.status = status
                self.headers = headers
                self.data = data

            def getheader(self, key, default=None):
                return self.headers.get(key, default)

            def read(self, limit):
                return self.data[:limit]

        class Connection:
            def __init__(self, response):
                self.response = response
                self.headers = None

            def request(self, method, path, headers):
                self.headers = headers

            def getresponse(self):
                return self.response

            def close(self):
                pass

        connection = Connection(
            Response(
                200,
                {"Content-Type": "application/json"},
                json.dumps(document()).encode(),
            )
        )
        with (
            patch(
                "text_list_builder.public_target",
                return_value=(
                    urlsplit("https://example.com/catalogue.json"),
                    "8.8.8.8",
                ),
            ),
            patch(
                "catalogue_feed.http.client.HTTPSConnection", return_value=connection
            ),
            patch("catalogue_feed.socket.create_connection"),
            patch("catalogue_feed.ssl.create_default_context"),
        ):
            self.assertEqual(
                feed.download("https://example.com/catalogue.json")["version"], 1
            )
        self.assertNotIn("Authorization", connection.headers)
        self.assertNotIn("Cookie", connection.headers)
        redirect = Connection(
            Response(302, {"Location": "https://private.example/catalogue.json"})
        )
        with (
            patch(
                "text_list_builder.public_target",
                side_effect=[
                    (urlsplit("https://example.com/catalogue.json"), "8.8.8.8"),
                    ValueError("Private target"),
                ],
            ) as validate,
            patch("catalogue_feed.http.client.HTTPSConnection", return_value=redirect),
            patch("catalogue_feed.socket.create_connection"),
            patch("catalogue_feed.ssl.create_default_context"),
        ):
            with self.assertRaisesRegex(ValueError, "Private"):
                feed.download("https://example.com/catalogue.json")
        self.assertEqual(validate.call_count, 2)


class ManifestTests(unittest.TestCase):
    def test_manifest_has_no_private_state_or_artwork_and_does_not_install(self):
        doc = {
            "version": 2,
            "lists": [
                {
                    "id": "one",
                    "name": "One",
                    "version": 2,
                    "items": [{"title": "A"}],
                    "poster": "image",
                    "private": "secret",
                }
            ],
        }
        value = feed.manifest(doc)
        self.assertNotIn("poster", value["lists"][0])
        self.assertNotIn("items", value["lists"][0])
        before = {"version": 1, "lists": [{"id": "one", "version": 1}]}
        self.assertEqual(feed.check_manifest(before, value)["count"], 1)
        self.assertEqual(before["version"], 1)
        self.assertEqual(
            feed.manifest_url("https://example.com/official-lists.json"),
            "https://example.com/official-lists.manifest.json",
        )
