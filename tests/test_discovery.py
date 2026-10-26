# SPDX-License-Identifier: AGPL-3.0-only
import unittest
from unittest.mock import patch
import providers


class DiscoveryTests(unittest.TestCase):
    def test_combined_credits_merge_roles_without_merging_movie_tv_ids(self):
        responses = [
            {
                "name": "Example Person",
                "profile_path": "/portrait.jpg",
                "biography": "Biography text",
                "known_for_department": "Acting",
            },
            {
                "cast": [
                    {
                        "id": 7,
                        "media_type": "movie",
                        "title": "Film",
                        "character": "Hero",
                        "release_date": "2020-01-01",
                    },
                    {
                        "id": 7,
                        "media_type": "tv",
                        "name": "Series",
                        "character": "Self",
                    },
                ],
                "crew": [
                    {"id": 7, "media_type": "movie", "title": "Film", "job": "Director"}
                ],
            },
        ]
        with patch("providers.cached_tmdb", side_effect=responses):
            result = providers.discovery("person", "12", {})
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["roles"], ["Hero", "Director"])
        self.assertEqual({r["type"] for r in result["items"]}, {"movie", "show"})
        self.assertEqual(result["profile"]["biography"], "Biography text")
        self.assertEqual(
            result["profile"]["photo"], "https://image.tmdb.org/t/p/w342/portrait.jpg"
        )

    def test_collection_members_remain_distinct_from_recommendations(self):
        responses = [
            {"title": "First", "belongs_to_collection": {"id": 9}},
            {
                "name": "Series collection",
                "parts": [{"id": 1, "title": "First"}, {"id": 2, "title": "Sequel"}],
            },
            {
                "results": [
                    {"id": 2, "title": "Sequel"},
                    {"id": 3, "title": "Unrelated"},
                ]
            },
        ]
        with patch("providers.cached_tmdb", side_effect=responses):
            result = providers.discovery("movie", "1", {})
        self.assertEqual([r["tmdb"] for r in result["items"]], ["2", "3"])
        self.assertEqual(result["items"][0]["group"], "Series collection")
        self.assertIn("not confirmed", result["items"][1]["group"])

    def test_invalid_identifier_never_reaches_provider(self):
        with patch("providers.cached_tmdb") as lookup:
            for value in ("../secret", "0", "-1", None):
                with self.assertRaises(ValueError):
                    providers.discovery("person", value, {})
        lookup.assert_not_called()

    def test_episode_related_id_is_parent_and_people_keep_ids(self):
        parent = {
            "name": "Parent",
            "created_by": [{"id": 33, "name": "Creator"}],
            "production_companies": [{"id": 77, "name": "Studio"}],
        }
        episode = {
            "name": "Episode",
            "credits": {
                "cast": [{"id": 44, "name": "Actor"}],
                "crew": [
                    {"id": 55, "name": "Producer", "job": "Producer"},
                    {"id": 66, "name": "Director", "job": "Director"},
                ],
            },
        }
        with patch("providers.cached_tmdb", side_effect=[parent, episode]):
            result = providers.title_details(
                {
                    "type": "episode",
                    "title": "Episode",
                    "tmdb": "99",
                    "show_tmdb": "10",
                    "season": "1",
                    "episode": "1",
                },
                {"tmdb": {"key": "test"}},
            )
        self.assertEqual(result["related_id"], "10")
        self.assertEqual(result["creator_people"][0]["id"], 33)
        self.assertEqual(result["cast"][0]["id"], 44)
        self.assertEqual(result["studios"][0]["id"], 77)
        self.assertEqual(result["producer_people"][0]["id"], 55)
        self.assertEqual(result["director_people"][0]["id"], 66)
        self.assertNotIn("publishers", result)

    def test_company_projects_keep_movie_and_tv_ids_separate(self):
        responses = [
            {"name": "Studio"},
            {"results": [{"id": 7, "title": "Film"}]},
            {"results": [{"id": 7, "name": "Series"}]},
        ]
        with patch("providers.cached_tmdb", side_effect=responses) as lookup:
            result = providers.discovery("company", "77", {})
        self.assertEqual({r["key"] for r in result["items"]}, {"movie:7", "tv:7"})
        self.assertIn("first page", result["note"])
        self.assertIn("with_companies=77", lookup.call_args_list[1].args[0])


class DiscoveryHTTPTests(unittest.TestCase):
    def test_title_browsing_is_read_only_and_checks_identifier(self):
        import json
        import tempfile
        import threading
        import urllib.request
        import urllib.error
        from pathlib import Path
        import app

        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch("app.DATA", Path(folder)),
        ):
            app.save_state({"settings": {}, "lists": []})
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            headers = {"Host": "127.0.0.1:8765", "X-Listweavarr-Token": app.SESSION}

            def request(body):
                return urllib.request.urlopen(
                    urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/title",
                        data=json.dumps(body).encode(),
                        headers=headers,
                    )
                )

            try:
                with (
                    patch(
                        "providers.title_details",
                        return_value={
                            "title": "Resolved title",
                            "release_date": "2020-01-01",
                        },
                    ) as details,
                    patch("app.request_item") as download,
                ):
                    with request({"type": "movie", "tmdb": "7"}) as response:
                        result = json.load(response)
                    self.assertEqual(result["item"]["title"], "Resolved title")
                    self.assertEqual(result["item"]["tmdb"], "7")
                    self.assertEqual(app.read_state()["lists"], [])
                    download.assert_not_called()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request({"type": "movie", "tmdb": "../secret"})
                    error.exception.close()
                    details.assert_called_once()
                    details.return_value = {
                        "title": "Pilot",
                        "show_title": "Parent show",
                    }
                    with request(
                        {"type": "episode", "tmdb": "10", "season": 0, "episode": 1}
                    ) as response:
                        episode_page = json.load(response)
                    self.assertEqual(episode_page["item"]["show_tmdb"], "10")
                    self.assertEqual(episode_page["item"]["season"], "0")
                    self.assertEqual(episode_page["item"]["episode"], "1")
                    self.assertNotIn("tmdb", episode_page["item"])
                    self.assertEqual(app.read_state()["lists"], [])
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request(
                            {"type": "episode", "tmdb": "10", "season": 1, "episode": 0}
                        )
                    error.exception.close()
                    details.return_value = {
                        "title": "Resolved title",
                        "release_date": "2020-01-01",
                    }
                    save_request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/title/save",
                        data=json.dumps(
                            {"type": "movie", "tmdb": "7", "title": "Untrusted label"}
                        ).encode(),
                        headers=headers,
                    )
                    with patch(
                        "app.compare",
                        side_effect=lambda rows, settings: [
                            dict(r, status="missing") for r in rows
                        ],
                    ):
                        with urllib.request.urlopen(save_request) as response:
                            entry = json.load(response)["entry"]
                    self.assertEqual(entry["name"], "Resolved title")
                    self.assertEqual(entry["items"][0]["status"], "missing")
                    self.assertEqual(len(app.read_state()["lists"]), 1)
                    download.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_save_uses_provider_rows_compares_and_never_downloads(self):
        import json
        import tempfile
        import threading
        import urllib.request
        from pathlib import Path
        import app

        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch("app.DATA", Path(folder)),
        ):
            app.save_state({"settings": {}, "lists": []})
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            payload = {
                "kind": "person",
                "identifier": "12",
                "keys": ["movie:7"],
                "items": [{"tmdb": "999"}],
            }
            provider = {
                "name": "Person",
                "note": "Provider credits",
                "items": [
                    {
                        "key": "movie:7",
                        "type": "movie",
                        "title": "Exact film",
                        "tmdb": "7",
                    },
                    {"key": "movie:8", "type": "movie", "title": "Other", "tmdb": "8"},
                ],
            }

            def compared(rows, settings):
                return [dict(r, status="missing") for r in rows]

            try:
                headers = {"Host": "127.0.0.1:8765", "X-Listweavarr-Token": app.SESSION}
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/discover/save",
                    data=json.dumps(payload).encode(),
                    headers=headers,
                )
                with (
                    patch("providers.discovery", return_value=provider),
                    patch("app.compare", side_effect=compared) as compare,
                    patch("app.request_item") as download,
                ):
                    with urllib.request.urlopen(request) as response:
                        result = json.load(response)["entry"]
                self.assertEqual(len(result["items"]), 1)
                self.assertEqual(result["items"][0]["tmdb"], "7")
                self.assertEqual(result["items"][0]["status"], "missing")
                self.assertEqual(app.read_state()["lists"][0]["id"], result["id"])
                compare.assert_called_once()
                download.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
