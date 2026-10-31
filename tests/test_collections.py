# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
import app
import saved_lists
import release_watch


class CollectionTests(unittest.TestCase):
    def test_portrait_poster_edit_marks_linked_playlist_for_review(self):
        import base64

        entry = {
            "id": "list",
            "name": "List",
            "items": [],
            "playlist": {"key": "7", "server": "http://plex"},
        }
        image = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
        )
        result = saved_lists.edit(
            entry,
            {
                "revision": saved_lists.revision(entry),
                "name": "List",
                "items": [],
                "poster": image,
            },
            app.normalize,
        )
        self.assertEqual(result["playlist"], entry["playlist"])
        self.assertTrue(result["playlist_needs_update"])

    def test_link_presentation_preserves_source_membership_requires_confirmation(self):
        entry = {
            "id": "list",
            "name": "Old",
            "source": "https://example.com/list",
            "items": [
                {
                    "id": "a",
                    "type": "movie",
                    "title": "A",
                    "tmdb": "1",
                    "status": "available",
                }
            ],
        }
        body = {
            "revision": saved_lists.revision(entry),
            "name": "Renamed",
            "description": "Description",
            "items": [{"id": "a"}],
        }
        renamed = saved_lists.edit(entry, body, app.normalize)
        self.assertEqual(renamed["source"], entry["source"])
        self.assertEqual(renamed["items"], entry["items"])
        body["items"].append({"type": "movie", "title": "B", "tmdb": "2"})
        with self.assertRaisesRegex(ValueError, "Confirm"):
            saved_lists.edit(entry, body, app.normalize)
        body["confirm_detach"] = True
        local = saved_lists.edit(entry, body, app.normalize)
        self.assertIsNone(local["source"])
        self.assertEqual(local["original_source"], entry["source"])
        self.assertFalse(local["followed"])
        self.assertEqual(len(entry["items"]), 1)
        self.assertEqual(len(local["items"]), 2)
        body["revision"] = "stale"
        with self.assertRaisesRegex(ValueError, "changed"):
            saved_lists.edit(entry, body, app.normalize)

    def test_reorder_and_remove_detach_and_duplicate_ids_rejected(self):
        entry = {
            "id": "list",
            "name": "Old",
            "source": "https://example.com/list",
            "items": [
                {"id": "a", "type": "movie", "title": "A"},
                {"id": "b", "type": "movie", "title": "B"},
            ],
        }
        base = {"revision": saved_lists.revision(entry), "name": "Order"}
        for items in ([{"id": "b"}, {"id": "a"}], [{"id": "b"}]):
            with self.assertRaisesRegex(ValueError, "Confirm"):
                saved_lists.edit(entry, dict(base, items=items), app.normalize)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            saved_lists.edit(
                entry, dict(base, items=[{"id": "a"}, {"id": "a"}]), app.normalize
            )
        with self.assertRaises(ValueError):
            saved_lists.poster("data:image/svg+xml;base64,AAAA")
        with self.assertRaises(ValueError):
            saved_lists.poster("data:image/png;base64,AAAA")

    def test_future_movies_and_tv_monitored_without_search_commands(self):
        calls = []

        def call(settings, service, path, payload=None, method=None):
            calls.append((service, path, payload, method))
            if path == "qualityprofile":
                return [{"id": 1}]
            if path == "rootfolder":
                return [{"path": "/media"}]
            if path in ("movie", "series") and payload is None:
                return []
            if path.startswith("movie/lookup"):
                return {"tmdbId": 1}
            if path.startswith("series/lookup"):
                return [
                    {"tvdbId": 2, "seasons": [{"seasonNumber": 0}, {"seasonNumber": 1}]}
                ]
            return payload

        release_watch.monitor({"type": "movie", "tmdb": "1"}, {}, 1, "/media", call)
        movie = next(c[2] for c in calls if c[1] == "movie" and c[2])
        self.assertEqual(movie["minimumAvailability"], "released")
        self.assertFalse(movie["addOptions"]["searchForMovie"])
        with patch("providers.cached_tmdb", return_value={"tvdb_id": 2}):
            release_watch.monitor({"type": "show", "tmdb": "2"}, {}, 1, "/media", call)
        series = next(c[2] for c in calls if c[1] == "series" and c[2])
        self.assertEqual(series["monitorNewItems"], "all")
        self.assertFalse(series["addOptions"]["searchForMissingEpisodes"])
        self.assertFalse(series["seasons"][0]["monitored"])
        self.assertTrue(series["seasons"][1]["monitored"])
        self.assertFalse(any(c[1] == "command" for c in calls))

    def test_bulk_routes_mixed_picks_atomically_and_deduplicates(self):
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch.object(app, "DATA", Path(folder)),
        ):
            app.save_state({"settings": {}, "lists": []})
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

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

            def metadata(path, settings):
                return {
                    "title": "Film",
                    "name": "Series",
                    "release_date": "2020-01-01",
                    "first_air_date": "2020-01-01",
                    "poster_path": "/poster.jpg",
                }

            try:
                with (
                    patch("providers.cached_tmdb", side_effect=metadata),
                    patch(
                        "release_watch.availability",
                        side_effect=lambda ident, *args: {
                            "status": "home" if ident == "1" else "theatrical"
                        },
                    ),
                    patch(
                        "release_watch.tv_availability",
                        return_value={"status": "premiered"},
                    ),
                    patch.object(app, "request_item") as downloads,
                ):
                    result = post(
                        "explore/route",
                        {
                            "items": [
                                {"type": "movie", "tmdb": "1"},
                                {"type": "movie", "tmdb": "2"},
                                {"type": "movie", "tmdb": "2"},
                                {"type": "show", "tmdb": "3"},
                            ]
                        },
                    )
                    self.assertEqual(result["tracked"], 1)
                    self.assertEqual(result["compared"], 2)
                    self.assertEqual(len(result["items"]), 1)
                    self.assertTrue(result["items"][0]["poster"])
                    self.assertEqual(len(app.read_state()["lists"]), 1)
                    post("explore/route", {"items": [{"type": "movie", "tmdb": "2"}]})
                    self.assertEqual(len(app.read_state()["release_watchlist"]), 1)
                    downloads.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_playlist_poster_upload_and_selection_uses_resource_rating_key(self):
        before = ET.fromstring(
            '<MediaContainer><Photo ratingKey="old" selected="1"/></MediaContainer>'
        )
        uploaded = ET.fromstring(
            '<MediaContainer><Photo ratingKey="old"/><Photo ratingKey="upload://new" selected="0"/></MediaContainer>'
        )
        verified = ET.fromstring(
            '<MediaContainer><Photo ratingKey="upload://new" selected="1"/></MediaContainer>'
        )
        import base64

        poster = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode()
        )
        with patch.object(
            app,
            "remote",
            side_effect=[
                before,
                ET.Element("MediaContainer"),
                uploaded,
                ET.Element("MediaContainer"),
                verified,
            ],
        ) as remote:
            app.upload_playlist_poster(
                "12", poster, {"url": "http://plex", "key": "secret"}
            )
        self.assertIsInstance(remote.call_args_list[1].kwargs["payload"], bytes)
        self.assertEqual(
            remote.call_args_list[3].args[1],
            "/library/metadata/12/poster?url=upload%3A%2F%2Fnew",
        )
