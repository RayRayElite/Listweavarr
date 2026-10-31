# SPDX-License-Identifier: AGPL-3.0-only
import json
import socket
import tempfile
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
import app


class ImportsAndMatching(unittest.TestCase):
    def test_letterboxd_export(self):
        item = app.import_items(
            "\ufeffName,Year,Letterboxd URI\nIron Man,2008,https://letterboxd.com/film/iron-man/\n",
            "csv",
        )[0]
        self.assertEqual(
            (item["title"], item["year"], item["type"]), ("Iron Man", "2008", "movie")
        )

    def test_imdb_movie_export(self):
        item = app.import_items(
            "Const,Title,Title Type,Year\ntt0371746,Iron Man,Movie,2008", "csv"
        )[0]
        self.assertEqual(item["imdb"], "tt0371746")

    def test_episode_requires_coordinates(self):
        with self.assertRaises(ValueError):
            app.import_items(
                json.dumps([{"title": "Pilot", "type": "episode"}]), "json"
            )

    def test_parent_id_is_used_for_episodes(self):
        catalog = [
            {
                "type": "show",
                "title": "Agents of S.H.I.E.L.D.",
                "ids": {"tvdb": "263365"},
            }
        ]
        item = app.normalize(
            {
                "title": "Pilot",
                "type": "episode",
                "show_tvdb": "263365",
                "season": 1,
                "episode": 1,
                "tmdb": 123,
            }
        )
        matches, basis = app.match_item(item, catalog)
        self.assertEqual(matches, catalog)
        self.assertEqual(basis, "provider ID")

    def test_conflicting_ids_do_not_match(self):
        matches, _ = app.match_item(
            {"type": "movie", "title": "Wrong", "tmdb": "1", "imdb": "tt2"},
            [{"type": "movie", "ids": {"tmdb": "1", "imdb": "tt3"}}],
        )
        self.assertEqual(matches, [])


class ScopedRequests(unittest.TestCase):
    def test_new_series_waits_for_metadata_then_searches_only_selected_episode(self):
        reads = 0

        def delayed(settings, service, path, payload=None, method=None):
            nonlocal reads
            if path == "series":
                self.calls.append((path, payload, method))
                return [] if payload is None else {**payload, "id": 7}
            if path.startswith("series/lookup"):
                self.calls.append((path, payload, method))
                return [
                    {
                        "title": "Example",
                        "tvdbId": 263365,
                        "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}],
                    }
                ]
            if path == "episode?seriesId=7":
                reads += 1
                if reads < 3:
                    self.calls.append((path, payload, method))
                    return []
            return self.fake_call(settings, service, path, payload, method)

        with (
            patch("app.arr_call", side_effect=delayed),
            patch("app.time.sleep") as sleep,
        ):
            result = app.request_item(
                {
                    "type": "episode",
                    "title": "Example",
                    "show_tvdb": "263365",
                    "season": "1",
                    "episode": "2",
                },
                {},
                1,
                "/tv",
            )
        self.assertEqual(reads, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            sum(
                path == "series" and payload is not None
                for path, payload, _ in self.calls
            ),
            1,
        )
        searches = [payload for path, payload, _ in self.calls if path == "command"]
        self.assertEqual(searches, [{"name": "EpisodeSearch", "episodeIds": [11]}])
        self.assertIn("1 missing episodes", result)

    def test_metadata_wait_is_bounded_and_never_searches_unknown_scope(self):
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        def empty(settings, service, path, payload=None, method=None):
            if path == "episode?seriesId=7":
                self.calls.append((path, payload, method))
                return []
            return self.fake_call(settings, service, path, payload, method)

        with (
            patch("app.arr_call", side_effect=empty),
            patch("app.time.monotonic", side_effect=lambda: clock[0]),
            patch("app.time.sleep", side_effect=sleep),
            self.assertRaisesRegex(ValueError, "No episode search was submitted"),
        ):
            app.request_item(
                {
                    "type": "episode",
                    "title": "Example",
                    "show_tvdb": "263365",
                    "season": "1",
                    "episode": "2",
                },
                {},
                1,
                "/tv",
            )
        self.assertEqual(clock[0], 20)
        self.assertFalse(
            any(path in ("command", "episode/monitor") for path, _, _ in self.calls)
        )

    def test_ready_metadata_does_not_wait(self):
        with patch("app.time.sleep") as sleep:
            self.run_scope("episode", [11])
        sleep.assert_not_called()

    def fake_call(self, settings, service, path, payload=None, method=None):
        self.calls.append((path, payload, method))
        return {
            "qualityprofile": [{"id": 1}],
            "rootfolder": [{"path": "/tv"}],
            "series": [{"id": 7, "tvdbId": 263365}],
            "episode?seriesId=7": [
                {"id": 10, "seasonNumber": 1, "episodeNumber": 1, "hasFile": False},
                {"id": 11, "seasonNumber": 1, "episodeNumber": 2, "hasFile": False},
                {"id": 12, "seasonNumber": 2, "episodeNumber": 1, "hasFile": False},
                {"id": 13, "seasonNumber": 0, "episodeNumber": 1, "hasFile": False},
            ],
        }.get(path, {})

    def setUp(self):
        self.calls = []

    def run_scope(self, kind, expected):
        item = {
            "title": "Example",
            "type": kind,
            "show_tvdb": "263365",
            "tvdb": "263365",
            "season": "1",
            "episode": "2",
        }
        with patch("app.arr_call", side_effect=self.fake_call):
            app.request_item(item, {}, 1, "/tv")
        command = next(payload for path, payload, _ in self.calls if path == "command")
        monitor = next(
            payload for path, payload, _ in self.calls if path == "episode/monitor"
        )
        self.assertEqual(command["episodeIds"], expected)
        self.assertEqual(monitor["episodeIds"], expected)
        self.assertFalse(
            any(
                path == "series" and payload is not None
                for path, payload, _ in self.calls
            )
        )

    def test_episode_does_not_search_other_episodes(self):
        self.run_scope("episode", [11])

    def test_season_does_not_search_other_seasons(self):
        self.run_scope("season", [10, 11])

    def test_show_excludes_specials(self):
        self.run_scope("show", [10, 11, 12])

    def test_invalid_destination_prevents_mutation(self):
        with (
            patch("app.arr_call", side_effect=self.fake_call),
            self.assertRaises(ValueError),
        ):
            app.request_item({"type": "show"}, {}, 99, "/tv")
        self.assertFalse(any(payload is not None for _, payload, _ in self.calls))


class LocalHTTPWorkflow(unittest.TestCase):
    def test_disk_full_comparison_preserves_saved_state_and_explains_storage(self):
        import errno

        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as directory,
            patch("app.DATA", Path(directory)),
        ):
            original = {
                "settings": {},
                "lists": [{"id": "test", "name": "Test", "items": []}],
            }
            app.save_state(original, backup=False)
            before = (app.DATA / "state.json").read_bytes()
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with (
                    patch("app.compare", return_value=[]),
                    patch(
                        "app.save_state", side_effect=OSError(errno.ENOSPC, "disk full")
                    ),
                ):
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/compare",
                        data=json.dumps({"list_id": "test"}).encode(),
                        headers={
                            "Host": "127.0.0.1:8765",
                            "X-Listweavarr-Token": app.SESSION,
                        },
                    )
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(request)
                    self.assertEqual(caught.exception.code, 507)
                    message = json.load(caught.exception)["error"]
                    caught.exception.close()
                    self.assertIn("disk space", message)
                    self.assertNotIn("connection settings", message)
                self.assertEqual((app.DATA / "state.json").read_bytes(), before)
            finally:
                server.shutdown()
                server.server_close()

    def test_import_persists_and_requires_session_token(self):
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as directory,
            patch("app.DATA", Path(directory)),
        ):
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            headers = {"Host": "127.0.0.1:8765"}
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(base + "/api/state", headers=headers)
                ) as response:
                    initial = json.load(response)
                payload = json.dumps(
                    {
                        "name": "Test",
                        "format": "csv",
                        "content": "type,title,tmdb\nmovie,Iron Man,1726",
                    }
                ).encode()
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(
                        urllib.request.Request(
                            base + "/api/import", data=payload, headers=headers
                        )
                    )
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                headers["X-Listweavarr-Token"] = initial["csrf"]
                with urllib.request.urlopen(
                    urllib.request.Request(
                        base + "/api/import", data=payload, headers=headers
                    )
                ) as response:
                    imported = json.load(response)
                self.assertEqual(imported["items"][0]["tmdb"], "1726")
                self.assertEqual(app.read_state()["lists"][0]["name"], "Test")
                correction = json.dumps(
                    {
                        "list_id": imported["id"],
                        "item_id": imported["items"][0]["id"],
                        "fields": {"title": "Iron Man"},
                        "plex_key": "100",
                    }
                ).encode()
                catalog = [
                    {
                        "key": "100",
                        "type": "movie",
                        "title": "Iron Man",
                        "year": "2008",
                        "ids": {"tmdb": "1726", "imdb": "tt0371746"},
                        "library": "Movies",
                    }
                ]
                with app.LOCK:
                    saved = app.read_state()
                    saved["settings"]["plex"] = {
                        "url": "http://nas",
                        "key": "hidden-token",
                    }
                    app.save_state(saved)
                with (
                    patch("app.plex_catalog", return_value=catalog),
                    urllib.request.urlopen(
                        urllib.request.Request(
                            base + "/api/correct", data=correction, headers=headers
                        )
                    ) as response,
                ):
                    corrected = json.load(response)["items"][0]
                self.assertEqual(corrected["correction"]["imdb"], "tt0371746")
                self.assertEqual(corrected["plex_override"], "100")
                with urllib.request.urlopen(
                    urllib.request.Request(base + "/api/state", headers=headers)
                ) as response:
                    self.assertNotIn("hidden-token", response.read().decode())
                for asset in (
                    "/",
                    "/style.css",
                    "/app.js",
                    "/trakt.js",
                    "/enrichment.js",
                    "/explore.js",
                ):
                    with urllib.request.urlopen(
                        urllib.request.Request(base + asset, headers=headers)
                    ) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(
                            response.headers.get("Cache-Control"), "no-store"
                        )
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


class PlexLogin(unittest.TestCase):
    def setUp(self):
        self.state = {
            "settings": {
                "plex": {"key": "old-server-secret", "url": "http://old:32400"}
            },
            "lists": [],
        }

    def test_login_url_uses_plex_and_local_return_without_token(self):
        with patch(
            "app.plex_account",
            return_value={"id": 12, "code": "strong-pin-code", "expiresIn": 600},
        ):
            self.state["plex_auth"] = {"client_id": "stable-client-id"}
            result = app.start_plex_login(self.state)
        parsed = urllib.parse.urlparse(result["url"])
        fields = urllib.parse.parse_qs(parsed.fragment.lstrip("?"))
        self.assertEqual(parsed.netloc, "app.plex.tv")
        self.assertEqual(fields["forwardUrl"], ["http://127.0.0.1:8765/#plex-login"])
        self.assertEqual(fields["clientID"], ["stable-client-id"])
        self.assertNotIn("authToken", result["url"])
        self.assertEqual(self.state["plex_auth"]["pin"]["id"], 12)

    def test_completed_login_clears_previous_server_and_redacts_secrets(self):
        self.state["plex_auth"] = {
            "client_id": "client",
            "pin": {"id": 12, "code": "secret-code", "expires": app.time.time() + 600},
        }
        with patch(
            "app.plex_account",
            side_effect=[{"authToken": "account-secret"}, {"username": "Test user"}],
        ):
            result = app.check_plex_login(self.state)
        self.assertTrue(result["signed_in"])
        self.assertNotIn("plex", self.state["settings"])
        public = json.dumps(app.public_state(self.state))
        self.assertNotIn("account-secret", public)
        self.assertNotIn("secret-code", public)
        self.assertNotIn("client_id", public)
        self.assertNotIn("pin", self.state["plex_auth"])

    def test_pending_pin_does_not_connect_or_replace_credentials(self):
        self.state["plex_auth"] = {
            "pin": {"id": 12, "code": "code", "expires": app.time.time() + 600}
        }
        with patch("app.plex_account", return_value={"authToken": None}):
            result = app.check_plex_login(self.state)
        self.assertTrue(result["pending"])
        self.assertEqual(self.state["settings"]["plex"]["key"], "old-server-secret")

    def test_only_local_plex_ipv4_hosts_are_accepted(self):
        self.assertEqual(
            app.plex_direct_ip("192-168-1-20.example.plex.direct"), "192.168.1.20"
        )
        for host in (
            "192-168-1-20.example.com",
            "8-8-8-8.example.plex.direct",
            "127-0-0-1.example.plex.direct",
            "invalid.plex.direct",
            None,
        ):
            self.assertIsNone(app.plex_direct_ip(host))

    def test_dns_failure_uses_https_fallback(self):
        url = "https://192-168-1-20.example.plex.direct:32400"
        xml = ET.fromstring('<MediaContainer machineIdentifier="nas"/>')
        with (
            patch(
                "app.urllib.request.urlopen",
                side_effect=urllib.error.URLError(socket.gaierror("DNS failure")),
            ),
            patch("app.plex_direct_request", return_value=xml) as fallback,
        ):
            self.assertIs(
                app.remote(url, "/library/sections", "secret", plex=True), xml
            )
        self.assertEqual(
            fallback.call_args.args[0].hostname, "192-168-1-20.example.plex.direct"
        )
        self.assertEqual(fallback.call_args.args[1], "/library/sections")

    def test_dns_fallback_preserves_poster_upload_bytes(self):
        raw = b"\x89PNG\r\n\x1a\nposter"
        with (
            patch(
                "app.urllib.request.urlopen",
                side_effect=urllib.error.URLError(socket.gaierror("DNS failure")),
            ),
            patch("app.PlexDirectHTTPSConnection") as connection,
        ):
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b""
            app.remote(
                "https://192-168-1-20.example.plex.direct:32400",
                "/library/metadata/12/posters",
                "secret",
                payload=raw,
                method="POST",
                plex=True,
            )
        request = connection.return_value.request
        self.assertEqual(
            request.call_args.args, ("POST", "/library/metadata/12/posters")
        )
        self.assertEqual(request.call_args.kwargs["body"], raw)
        self.assertEqual(
            request.call_args.kwargs["headers"]["Content-Type"],
            "application/octet-stream",
        )

    def test_other_network_errors_do_not_use_fallback(self):
        with (
            patch(
                "app.urllib.request.urlopen",
                side_effect=urllib.error.URLError(ConnectionRefusedError()),
            ),
            patch("app.plex_direct_request") as fallback,
            self.assertRaises(ValueError),
        ):
            app.remote(
                "https://192-168-1-20.example.plex.direct", "/", "secret", plex=True
            )
        fallback.assert_not_called()

    def test_tls_uses_original_hostname(self):
        connection = app.PlexDirectHTTPSConnection(
            "192-168-1-20.example.plex.direct", 32400, timeout=5
        )
        with (
            patch("app.socket.create_connection") as tcp,
            patch.object(connection._context, "wrap_socket") as tls,
        ):
            connection.connect()
        self.assertEqual(tcp.call_args.args[0], ("192.168.1.20", 32400))
        self.assertEqual(
            tls.call_args.kwargs["server_hostname"], "192-168-1-20.example.plex.direct"
        )
        self.assertTrue(connection._context.check_hostname)

    def test_expired_pin_is_cleared_without_network_call(self):
        self.state["plex_auth"] = {"pin": {"id": 12, "code": "code", "expires": 0}}
        with (
            patch("app.plex_account") as network,
            self.assertRaisesRegex(ValueError, "expired"),
        ):
            app.check_plex_login(self.state)
        network.assert_not_called()
        self.assertNotIn("pin", self.state["plex_auth"])

    def test_resources_do_not_return_server_tokens_to_browser(self):
        self.state["plex_auth"] = {"token": "account-secret"}
        resources = [
            {
                "provides": "server",
                "clientIdentifier": "nas",
                "name": "NAS",
                "owned": True,
                "accessToken": "server-secret",
                "connections": [],
            },
            {"provides": "player", "accessToken": "player-secret"},
            {"provides": "server", "accessToken": None},
        ]
        with patch("app.plex_account", return_value=resources):
            result = app.plex_servers(self.state)
        self.assertEqual(len(result["servers"]), 1)
        self.assertNotIn("secret", json.dumps(result))

    def test_server_identity_and_library_access_are_verified(self):
        resources = [
            {
                "clientIdentifier": "nas",
                "name": "NAS",
                "accessToken": "server-secret",
                "connections": [
                    {
                        "uri": "https://remote:32400",
                        "local": False,
                        "protocol": "https",
                    },
                    {"uri": "http://local:32400", "local": True, "protocol": "http"},
                ],
            }
        ]
        with (
            patch("app.plex_servers", return_value=resources),
            patch(
                "app.remote",
                side_effect=[
                    ET.fromstring('<MediaContainer machineIdentifier="nas"/>'),
                    ET.fromstring("<MediaContainer/>"),
                ],
            ) as network,
        ):
            result = app.connect_plex_server(self.state, "nas")
        self.assertEqual(result["url"], "http://local:32400")
        self.assertEqual(self.state["settings"]["plex"]["key"], "server-secret")
        self.assertEqual(network.call_args_list[1].args[1], "/library/sections")

    def test_wrong_server_does_not_overwrite_connection(self):
        resources = [
            {
                "clientIdentifier": "nas",
                "name": "NAS",
                "accessToken": "server-secret",
                "connections": [{"uri": "http://wrong:32400"}],
            }
        ]
        with (
            patch("app.plex_servers", return_value=resources),
            patch(
                "app.remote",
                return_value=ET.fromstring(
                    '<MediaContainer machineIdentifier="other"/>'
                ),
            ),
            self.assertRaises(ValueError),
        ):
            app.connect_plex_server(self.state, "nas")
        self.assertEqual(self.state["settings"]["plex"]["key"], "old-server-secret")


if __name__ == "__main__":
    unittest.main()
