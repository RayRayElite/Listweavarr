# SPDX-License-Identifier: AGPL-3.0-only
import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from unittest.mock import patch
import app
import backups
import playlist_artwork


class PlaylistArtworkTests(unittest.TestCase):
    def test_square_preference_uses_playlist_poster_without_changing_default(self):
        state = app.read_state()
        square = b"\x89PNG\r\n\x1a\nsquare"
        state["lists"][0]["playlist_poster"] = (
            "data:image/png;base64," + base64.b64encode(square).decode()
        )
        app.save_state(state)
        with self.request(
            "/api/playlist-companion/artwork?serverId=server&playlistId=7&shape=square"
        ) as response:
            self.assertEqual(response.read(), square)
        with self.request(
            "/api/playlist-companion/artwork?serverId=server&playlistId=7"
        ) as response:
            self.assertNotEqual(response.read(), square)

    def test_shared_posters_use_write_capability_and_preflight(self):
        state = app.read_state()
        state["playlist_progress_token"] = "p" * 43
        app.save_state(state)
        endpoint = "/api/playlist-companion/posters"
        body = {
            "scope": dict(serverId="server", userId="alice", playlistId="7"),
            "upload": {
                "mime": "image/png",
                "data": self.poster.split(",", 1)[1],
                "updatedAt": 1000,
            },
        }
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request(endpoint, method="POST", body=body)
        self.assertEqual(denied.exception.code, 403)
        with self.request(endpoint, method="OPTIONS") as response:
            self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])
        with self.request(
            endpoint, token="p" * 43, method="POST", body=body
        ) as response:
            self.assertEqual(
                json.load(response)["poster"]["data"], body["upload"]["data"]
            )

    def test_progress_endpoint_requires_separate_capability_and_preserves_profiles(
        self,
    ):
        state = app.read_state()
        state["playlist_progress_token"] = "p" * 43
        app.save_state(state)
        scope = dict(serverId="server", userId="alice", playlistId="7")
        row = dict(
            scope,
            schema=1,
            entryId="e",
            ratingKey="r",
            sessionId="session",
            offsetMs=500,
            revision=1,
            updatedAt=1000,
            ratingKeyOccurrences=1,
            completed=False,
        )
        endpoint = "/api/playlist-companion/progress"
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request(
                endpoint, method="POST", body={"scopes": [scope], "items": [row]}
            )
        self.assertEqual(denied.exception.code, 403)
        with self.request(
            endpoint,
            token="p" * 43,
            method="POST",
            body={"scopes": [scope], "items": [row]},
        ) as response:
            self.assertEqual(json.load(response)["items"], [row])
        with self.request(
            endpoint,
            token="p" * 43,
            method="POST",
            body={"scopes": [dict(scope, userId="bob")], "items": []},
        ) as response:
            self.assertEqual(json.load(response)["items"], [])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = patch.object(app, "DATA", Path(self.temp.name))
        self.data.start()
        self.addCleanup(self.data.stop)
        self.token = "a" * 43
        self.poster = (
            "data:image/png;base64,"
            + base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
        )
        app.save_state(
            {
                "settings": {
                    "plex": {"url": "http://plex.test:32400", "key": "private-plex-key"}
                },
                "lists": [
                    {
                        "id": "list",
                        "name": "Private list",
                        "items": [],
                        "poster": self.poster,
                        "playlist": {"key": "7", "server": "http://plex.test:32400"},
                    }
                ],
                "playlist_artwork_pairing": {
                    "token": self.token,
                    "machine": "server",
                    "server": "http://plex.test:32400",
                },
            }
        )
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(
        self,
        path="/api/playlist-companion/artwork",
        token=None,
        origin="https://app.plex.tv",
        method="GET",
        body=None,
    ):
        headers = {
            "Host": "127.0.0.1:8765",
            "Origin": origin,
            "Authorization": "Bearer " + (self.token if token is None else token),
            "X-Listweavarr-Token": app.SESSION,
            "Content-Type": "application/json",
        }
        request = urllib.request.Request(
            "http://127.0.0.1:" + str(self.server.server_port) + path,
            headers=headers,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
        )
        return urllib.request.urlopen(request)

    def test_scoped_catalogue_and_image_have_no_credentials_or_list_entries(self):
        with self.request() as response:
            data = json.load(response)
            self.assertEqual(
                response.headers["Access-Control-Allow-Origin"], "https://app.plex.tv"
            )
        self.assertEqual(data["items"][0]["playlistId"], "7")
        self.assertEqual(set(data["items"][0]), {"serverId", "playlistId", "revision"})
        with self.request(
            "/api/playlist-companion/artwork?serverId=server&playlistId=7"
        ) as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertTrue(response.read().startswith(b"\x89PNG"))

    def test_wrong_token_origin_and_target_are_rejected(self):
        for kwargs in ({"token": "wrong"}, {"origin": "https://unrelated.test"}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request(**kwargs)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/playlist-companion/artwork?serverId=other&playlistId=7")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()
        self.assertFalse(playlist_artwork.authorize(app.read_state(), "Bearer \u2603"))

    def test_pair_rotation_and_revocation_use_existing_csrf_boundary(self):
        with patch.object(
            app,
            "remote",
            return_value=ET.Element("MediaContainer", machineIdentifier="server"),
        ):
            with self.request(
                "/api/playlist-companion/pair", method="POST", body={}
            ) as response:
                token = json.load(response)["token"]
        self.assertNotEqual(token, self.token)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request()
        caught.exception.close()
        with self.request(
            "/api/playlist-companion/pair", method="POST", body={"revoke": True}
        ) as response:
            self.assertTrue(json.load(response)["revoked"])
        self.assertNotIn("playlist_artwork_pairing", app.public_state(app.read_state()))
        self.assertNotIn("playlist_artwork_pairing", backups.export(app.read_state()))

    def test_preflight_is_limited_to_artwork(self):
        with self.request(method="OPTIONS", token="") as response:
            self.assertEqual(
                response.headers["Access-Control-Allow-Methods"], "GET, OPTIONS"
            )
            self.assertNotIn("*", response.headers["Access-Control-Allow-Origin"])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/state", method="OPTIONS")
        caught.exception.close()

    def test_changed_plex_server_does_not_publish_stale_targets(self):
        state = app.read_state()
        state["settings"]["plex"]["url"] = "http://other.test:32400"
        self.assertEqual(playlist_artwork.catalogue(state)["items"], [])

    def test_legacy_artwork_mapping_requires_exact_order_not_title(self):
        state = app.read_state()
        state["lists"][0].pop("playlist")

        def remote(base, path, key, **kwargs):
            result = ET.Element("MediaContainer")
            if path.startswith("/playlists?"):
                ET.SubElement(
                    result,
                    "Playlist",
                    ratingKey="8",
                    leafCount="2",
                    title="A completely different name",
                )
            else:
                for value in ("201", "202"):
                    ET.SubElement(result, "Video", ratingKey=value)
            return result

        mappings = playlist_artwork.discover(
            state, "server", remote, lambda entry: {"keys": ["201", "202"]}
        )
        self.assertEqual(mappings[0]["playlistId"], "8")
        state["playlist_artwork_mappings"] = mappings
        self.assertEqual(
            playlist_artwork.catalogue(state)["items"][0]["playlistId"], "8"
        )
        self.assertNotIn(
            "playlist",
            state["lists"][0],
            "Artwork mapping must not confer publication ownership",
        )
        self.assertEqual(
            playlist_artwork.discover(
                state, "server", remote, lambda entry: {"keys": ["202", "201"]}
            ),
            [],
        )

    def test_pair_endpoint_cannot_be_called_with_artwork_capability_alone(self):
        request = urllib.request.Request(
            "http://127.0.0.1:"
            + str(self.server.server_port)
            + "/api/playlist-companion/pair",
            headers={"Host": "127.0.0.1:8765", "Authorization": "Bearer " + self.token},
            data=b"{}",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
