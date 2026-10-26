# SPDX-License-Identifier: AGPL-3.0-only
import json
import tempfile
import time
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import app
import providers


class ConnectionDraftTests(unittest.TestCase):
    def test_entered_radarr_address_is_used_without_saving(self):
        saved = {"radarr": {"url": "", "key": ""}}
        body = {
            "service": "radarr",
            "config": {
                "url": "\u00a0http://192.168.100.184:7878/\u00a0",
                "key": "draft-key",
            },
        }
        with patch("app.remote", return_value={"appName": "Radarr"}) as request:
            self.assertEqual(app.test_connection(saved, body), {"ok": True})
        self.assertEqual(
            request.call_args.args[:3],
            ("http://192.168.100.184:7878", "/api/v3/system/status", "draft-key"),
        )
        self.assertEqual(saved, {"radarr": {"url": "", "key": ""}})

    def test_blank_key_reuses_saved_key_with_new_sonarr_address(self):
        saved = {"sonarr": {"url": "http://old:8989", "key": "saved-key"}}
        body = {
            "service": "sonarr",
            "config": {"url": "http://192.168.100.184:8989", "key": ""},
        }
        with patch("app.remote", return_value={}) as request:
            app.test_connection(saved, body)
        self.assertEqual(
            request.call_args.args[:3],
            ("http://192.168.100.184:8989", "/api/v3/system/status", "saved-key"),
        )
        self.assertEqual(saved["sonarr"]["url"], "http://old:8989")

    def test_missing_address_explains_which_field_is_needed(self):
        with self.assertRaisesRegex(ValueError, "Radarr server address"):
            app.test_connection(
                {}, {"service": "radarr", "config": {"url": "", "key": "key"}}
            )

    def test_missing_key_explains_where_to_find_it(self):
        with self.assertRaisesRegex(ValueError, "Sonarr API key"):
            app.test_connection(
                {},
                {"service": "sonarr", "config": {"url": "http://nas:8989", "key": ""}},
            )

    def test_tmdb_tests_unsaved_token(self):
        with patch("providers.tmdb", return_value={}) as request:
            app.test_connection(
                {}, {"service": "tmdb", "config": {"key": "draft-token"}}
            )
        self.assertEqual(request.call_args.args[1]["tmdb"]["key"], "draft-token")


class SourceImportTests(unittest.TestCase):
    def test_letterboxd_preserves_order_and_ignores_recommendations(self):
        markup = """<h1 class="title-1">My list</h1>
        <div data-list-index="0" data-item-name="Second Movie (2020)" data-item-link="/film/second/"></div>
        <div data-list-index="1" data-item-name="First Movie (2019)" data-item-link="/film/first/"></div>
        <div data-item-name="Recommendation (2021)" data-item-link="/film/other/"></div>
        <a class="next" href="/me/list/test/page/2/">Next</a>"""
        name, rows, next_page = providers.parse_letterboxd(markup)
        self.assertEqual(name, "My list")
        self.assertEqual([r["title"] for r in rows], ["Second Movie", "First Movie"])
        self.assertEqual(rows[0]["year"], "2020")
        self.assertEqual(next_page, "/me/list/test/page/2/")

    def test_letterboxd_pagination_and_resolution(self):
        first = '<div data-list-index="0" data-item-name="One (2001)" data-item-link="/film/one/"></div><a class="next" href="/me/list/test/page/2/">Next</a>'
        second = '<div data-list-index="1" data-item-name="Two (2002)" data-item-link="/film/two/"></div>'
        with (
            patch("providers.fetch", side_effect=[first, second]),
            patch(
                "providers.film_ids",
                side_effect=lambda url: {"tmdb": "1" if "/one/" in url else "2"},
            ),
        ):
            result = providers.letterboxd(
                "https://letterboxd.com/me/list/test/", lambda *a: None
            )
        self.assertEqual([r["tmdb"] for r in result["items"]], ["1", "2"])

    def test_failed_film_resolution_keeps_entry_for_review(self):
        page = '<div data-list-index="0" data-item-name="One (2001)" data-item-link="/film/one/"></div>'
        with (
            patch("providers.fetch", return_value=page),
            patch("providers.film_ids", side_effect=ValueError("Unavailable")),
        ):
            result = providers.letterboxd(
                "https://letterboxd.com/me/list/test/", lambda *a: None
            )
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(len(result["warnings"]), 1)

    def test_provider_allowlist_rejects_other_hosts_and_credentials(self):
        for url in [
            "http://letterboxd.com/me/list/test/",
            "https://letterboxd.com.evil.test/",
            "https://user:password@letterboxd.com/me/list/test/",
            "https://127.0.0.1/list",
        ]:
            with self.assertRaises(ValueError):
                providers.validate_url(url)

    @staticmethod
    def card(ident, kind, title, tmdb):
        return f'<div class="card" data-media-id="{ident}" data-mediatype="{kind}"><div class="movie-title" title="{title} (2020)"></div><a href="https://www.themoviedb.org/{"movie" if kind == "movie" else "tv"}/{tmdb}">TMDB</a></div>'

    def test_mdblist_keeps_mixed_order_across_pages(self):
        first = (
            "<h3>Owner</h3><h3>Chronology</h3>Items: 3"
            + self.card("1", "movie", "One", 10)
            + self.card("2", "show", "Two", 20)
        )
        second = self.card("3", "movie", "Three", 30)
        with patch("providers.fetch", side_effect=[first, second]):
            result = providers.mdblist(
                "https://mdblist.com/lists/me/test", lambda *a: None
            )
        self.assertEqual(result["name"], "Chronology")
        self.assertEqual(
            [r["type"] for r in result["items"]], ["movie", "show", "movie"]
        )
        self.assertEqual([r["tmdb"] for r in result["items"]], ["10", "20", "30"])

    def test_mdblist_repeated_page_does_not_save_partial_list(self):
        page = "Items: 3" + self.card("1", "movie", "One", 10)
        with (
            patch("providers.fetch", return_value=page),
            self.assertRaisesRegex(ValueError, "repeated"),
        ):
            providers.mdblist("https://mdblist.com/lists/me/test", lambda *a: None)

    def test_imdb_csv_episode_is_retained_unresolved_without_tmdb(self):
        rows = app.import_items(
            "Const,Title,Title Type,Year\ntt123,Pilot,TV Episode,2020", "csv", {}
        )
        self.assertEqual(rows[0]["type"], "episode")
        self.assertTrue(rows[0]["metadata_unresolved"])
        self.assertEqual(rows[0]["imdb"], "tt123")

    def test_tmdb_episode_resolution_uses_exact_imdb_and_parent_ids(self):
        row = {
            "type": "episode",
            "title": "Pilot",
            "imdb": "tt123",
            "metadata_unresolved": True,
        }
        responses = [
            {
                "tv_episode_results": [
                    {"id": 100, "show_id": 200, "season_number": 1, "episode_number": 2}
                ]
            },
            {"tvdb_id": 300, "imdb_id": "tt456"},
        ]
        with patch("providers.tmdb", side_effect=responses):
            result = providers.enrich(row, {"tmdb": {"key": "secret"}})
        self.assertEqual(
            (
                result["show_tmdb"],
                result["show_tvdb"],
                result["season"],
                result["episode"],
            ),
            ("200", "300", "1", "2"),
        )
        self.assertNotIn("metadata_unresolved", result)

    def test_refresh_retains_saved_corrections_and_item_identity(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.DATA", Path(folder)):
            row = {
                "id": "old-id",
                "title": "Old",
                "type": "movie",
                "source_key": "stable",
                "correction": {"title": "Corrected", "tmdb": "9"},
            }
            app.save_state(
                {
                    "settings": {},
                    "lists": [
                        {
                            "id": "list",
                            "name": "List",
                            "source": "https://letterboxd.com/me/list/test/",
                            "items": [row],
                        }
                    ],
                }
            )
            result = {
                "name": "List",
                "source": "https://letterboxd.com/me/list/test/",
                "items": [{"title": "New", "type": "movie", "source_key": "stable"}],
                "warnings": [],
            }
            with patch("providers.import_url", return_value=result):
                job_id = app.start_import_job({"list_id": "list"})["job_id"]
                for _ in range(200):
                    with app.JOBS_LOCK:
                        job = dict(app.JOBS[job_id])
                    if job["status"] != "running":
                        break
                    time.sleep(0.01)
            self.assertEqual(job["status"], "complete", job)
            saved = app.read_state()["lists"][0]["items"][0]
            self.assertEqual(
                (saved["id"], saved["title"], saved["tmdb"]),
                ("old-id", "Corrected", "9"),
            )


class LibraryWorkflowTests(unittest.TestCase):
    def test_season_completeness_excludes_future_episodes(self):
        settings = {"sonarr": {"key": "secret"}}
        rows = [
            {"seasonNumber": 1, "episodeNumber": 1, "airDate": "2000-01-01"},
            {"seasonNumber": 1, "episodeNumber": 2, "airDate": "2999-01-01"},
            {"seasonNumber": 2, "episodeNumber": 1, "airDate": "2000-01-01"},
        ]
        with patch("app.arr_call", side_effect=[[{"id": 3, "tvdbId": 10}], rows]):
            expected, _ = app.expected_episodes(
                {"type": "season", "season": "1", "show_tvdb": "10"},
                {"ids": {}},
                settings,
                {},
            )
        self.assertEqual(expected, {("1", "1")})

    def test_episode_comparison_uses_episode_key_for_playlist(self):
        catalog = [
            {
                "key": "10",
                "type": "show",
                "title": "Show",
                "ids": {"tvdb": "20"},
                "library": "TV",
            }
        ]
        item = app.normalize(
            {
                "type": "episode",
                "title": "Pilot",
                "show_tvdb": "20",
                "season": 1,
                "episode": 2,
            }
        )
        leaves = [{"key": "99", "season": "1", "episode": "2"}]
        with (
            patch("app.plex_catalog", return_value=catalog),
            patch("app.plex_leaves", return_value=leaves),
        ):
            result = app.compare(
                [item], {"plex": {"url": "http://nas", "key": "secret"}}
            )[0]
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["plex_keys"], ["99"])
        self.assertEqual(result["plex_key"], "99")

    def test_manually_confirmed_match_overrides_title_only_review(self):
        catalog = [
            {
                "key": "10",
                "type": "movie",
                "title": "Different",
                "ids": {},
                "library": "Movies",
            }
        ]
        item = {
            "id": "i",
            "type": "movie",
            "title": "Source title",
            "plex_override": "10",
            "plex_server": "http://nas",
        }
        with patch("app.plex_catalog", return_value=catalog):
            result = app.compare(
                [item], {"plex": {"url": "http://nas", "key": "secret"}}
            )[0]
        self.assertEqual(result["status"], "available")

    def test_playlist_preview_preserves_interleaving_and_expanded_order(self):
        entry = {
            "name": "Chronology",
            "items": [
                {"status": "available", "plex_keys": ["movie"]},
                {"status": "partial", "plex_keys": ["e1", "e2"]},
                {"status": "missing"},
                {"status": "review", "plex_keys": ["unconfirmed"]},
                {"status": "available", "plex_keys": ["movie2"]},
            ],
        }
        plan = app.playlist_preview(entry)
        self.assertEqual(plan["keys"], ["movie", "e1", "e2", "movie2"])
        self.assertEqual(plan["omitted"], 2)

    def test_playlist_checks_order_before_deleting_previous(self):
        entry = {
            "name": "List",
            "items": [],
            "playlist": {"key": "5", "server": "http://nas", "title": "Old"},
        }
        rows = [{"status": "available", "plex_keys": ["1", "2"]}]
        responses = [
            ET.fromstring('<MediaContainer><Playlist title="Old"/></MediaContainer>'),
            ET.fromstring('<MediaContainer machineIdentifier="machine"/>'),
            ET.fromstring('<MediaContainer><Playlist ratingKey="6"/></MediaContainer>'),
            ET.fromstring(
                '<MediaContainer><Video ratingKey="2"/><Video ratingKey="1"/></MediaContainer>'
            ),
        ]
        with (
            patch("app.compare", return_value=rows),
            patch("app.remote", side_effect=responses) as remote,
            self.assertRaisesRegex(ValueError, "preserved"),
        ):
            app.create_playlist(
                entry, {"plex": {"url": "http://nas", "key": "secret"}}, "New", True
            )
        self.assertFalse(
            any(c.kwargs.get("method") == "DELETE" for c in remote.call_args_list)
        )

    def test_playlist_replaces_only_after_new_order_is_verified(self):
        entry = {
            "name": "List",
            "items": [],
            "playlist": {"key": "5", "server": "http://nas", "title": "Old"},
        }
        rows = [{"status": "available", "plex_keys": ["1", "2"]}]
        responses = [
            ET.fromstring('<MediaContainer><Playlist title="Old"/></MediaContainer>'),
            ET.fromstring('<MediaContainer machineIdentifier="machine"/>'),
            ET.fromstring('<MediaContainer><Playlist ratingKey="6"/></MediaContainer>'),
            ET.fromstring(
                '<MediaContainer><Video ratingKey="1"/><Video ratingKey="2"/></MediaContainer>'
            ),
            ET.Element("MediaContainer"),
        ]
        with (
            patch("app.compare", return_value=rows),
            patch("app.remote", side_effect=responses) as remote,
        ):
            result = app.create_playlist(
                entry, {"plex": {"url": "http://nas", "key": "secret"}}, "New", True
            )
        self.assertEqual(result["key"], "6")
        self.assertEqual(remote.call_args_list[-1].kwargs["method"], "DELETE")
        self.assertEqual(remote.call_args_list[-1].args[1], "/playlists/5")


if __name__ == "__main__":
    unittest.main()
