# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import artwork_cache
import snapshot_cache
import list_runtime
import app

PNG = "data:image/png;base64,iVBORw0KGgo="


class LoadingRuntimeTests(unittest.TestCase):
    def test_artwork_projection_keeps_original_and_bounds_cache(self):
        artwork_cache.clear()
        rows = [{"id": "a", "poster": PNG, "items": []}]
        result = artwork_cache.project(rows)
        self.assertEqual(rows[0]["poster"], PNG)
        key = result[0]["poster"].split("/")[-1]
        self.assertEqual(artwork_cache.get(key), ("image/png", b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(artwork_cache.project(rows), result)
        self.assertIsNone(artwork_cache.get("../state.json"))
        with patch.object(artwork_cache, "LIMIT", 0):
            artwork_cache.register(PNG)
        # Cache hits need no allocation; a new poster enforces eviction.
        with patch.object(artwork_cache, "LIMIT", 0):
            artwork_cache.register("data:image/png;base64,iVBORw0KGgp4")
        self.assertIsNone(artwork_cache.get(key))

    def test_snapshot_copies_external_changes_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            self.assertEqual(snapshot_cache.read(path, {}), {})
            path.write_text('{"lists": [{"id":"a"}]}')
            first = snapshot_cache.read(path, {})
            first["lists"].clear()
            self.assertEqual(len(snapshot_cache.read(path, {})["lists"]), 1)
            replacement = path.with_suffix(".tmp")
            replacement.write_text('{"lists": []}')
            replacement.replace(path)
            self.assertEqual(snapshot_cache.read(path, {}), {"lists": []})
            path.write_text("broken")
            with self.assertRaises(ValueError):
                snapshot_cache.read(path, {})

    def test_runtime_expands_scopes_estimates_and_preserves_repeats(self):
        metadata = {
            "movie/1": {"runtime": 100},
            "tv/2": {
                "episode_run_time": [25],
                "seasons": [
                    {"season_number": 0, "episode_count": 1},
                    {"season_number": 1, "episode_count": 2},
                    {"season_number": 2, "episode_count": 2},
                ],
            },
            "tv/2/season/0": {"episodes": [{"episode_number": 1, "runtime": 60}]},
            "tv/2/season/1": {
                "episodes": [
                    {"episode_number": 1, "runtime": 10},
                    {"episode_number": 2, "runtime": 20},
                ]
            },
        }
        with patch(
            "providers.peek_tmdb", side_effect=lambda path: metadata.get(path, {})
        ), patch(
            "providers.cached_tmdb",
            side_effect=AssertionError("Automatic totals must be cache-only"),
        ):
            result = list_runtime.summarize(
                [
                    {"type": "movie", "tmdb": "1"},
                    {"type": "movie", "tmdb": "1"},
                    {"type": "show", "tmdb": "2"},
                ]
            )
            self.assertEqual(result["minutes"], 280)
            self.assertEqual(result["known_units"], 4)
            self.assertEqual(result["estimated_units"], 2)
            self.assertTrue(result["complete"])
            special = list_runtime.summarize(
                [{"type": "episode", "show_tmdb": "2", "season": 0, "episode": 1}]
            )
            self.assertEqual(special["minutes"], 60)
            missing = list_runtime.summarize([{"type": "movie", "tmdb": "9"}])
            self.assertEqual(missing["unknown_entries"], 1)
            self.assertEqual(missing["minutes"], 0)

    def test_runtime_fill_is_bounded(self):
        metadata = {}

        def fetch(path, settings):
            metadata[path] = {"runtime": 90}
            return metadata[path]

        with patch(
            "providers.peek_tmdb", side_effect=lambda path: metadata.get(path, {})
        ), patch("providers.cached_tmdb", side_effect=fetch) as provider:
            result = list_runtime.fill(
                [{"type": "movie", "tmdb": str(index)} for index in range(30)],
                {"tmdb": {"key": "fixture"}},
            )
            self.assertEqual(provider.call_count, 20)
            self.assertEqual(result["unknown_entries"], 10)
            self.assertEqual(result["minutes"], 1800)


class BrowseTransportTests(unittest.TestCase):
    def test_private_artwork_gzip_and_runtime_routes(self):
        import base64
        import gzip
        import threading
        import urllib.request
        import urllib.error

        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            raw = b"\x89PNG\r\n\x1a\n" + b"x" * 12000
            uri = "data:image/png;base64," + base64.b64encode(raw).decode()
            app.save_state(
                {
                    "settings": {},
                    "lists": [
                        {
                            "id": "a",
                            "name": "Fixture",
                            "description": "x" * 9000,
                            "poster": uri,
                            "items": [
                                {
                                    "id": str(i),
                                    "type": "movie",
                                    "title": "Fixture title",
                                    "tmdb": "1",
                                }
                                for i in range(100)
                            ],
                        }
                    ],
                }
            )
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}"

            def request(path, headers=None, body=None):
                return urllib.request.urlopen(
                    urllib.request.Request(
                        base + path,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers={
                            "Host": "127.0.0.1:8765",
                            "X-Listweavarr-Token": app.SESSION,
                            **(headers or {}),
                        },
                    )
                )

            try:
                with request("/api/state", {"Accept-Encoding": "gzip"}) as response:
                    self.assertEqual(response.headers["Content-Encoding"], "gzip")
                    projected = json.loads(gzip.decompress(response.read()))
                art = projected["lists"][0]["poster"]
                self.assertTrue(art.startswith("/api/artwork/"))
                artwork_cache.clear()
                with request(art) as response:
                    self.assertEqual(response.read(), raw)
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                    self.assertIn("private", response.headers["Cache-Control"])
                    tag = response.headers["ETag"]
                with self.assertRaises(urllib.error.HTTPError) as unchanged:
                    request(art, {"If-None-Match": tag})
                self.assertEqual(unchanged.exception.code, 304)
                unchanged.exception.close()
                with request("/api/state", {"Accept-Encoding": "gzip;q=0"}) as response:
                    self.assertIsNone(response.headers.get("Content-Encoding"))
                    json.load(response)
                with request("/api/lists/revision", body={"list_id": "a"}) as response:
                    self.assertEqual(json.load(response)["entry"]["poster"], uri)
                with patch("providers.peek_tmdb", return_value={"runtime": 100}), patch(
                    "providers.cached_tmdb",
                    side_effect=AssertionError("No automatic network work"),
                ):
                    with request(
                        "/api/lists/runtime", body={"list_id": "a"}
                    ) as response:
                        self.assertEqual(json.load(response)["minutes"], 10000)
                self.assertEqual(app.read_state()["lists"][0]["poster"], uri)
            finally:
                server.shutdown()
                server.server_close()
