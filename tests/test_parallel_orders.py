# SPDX-License-Identifier: AGPL-3.0-only
"""Parallel scopes are explicit, verified and interleaved without losing tails."""
import unittest
import json
import threading
import urllib.request
from unittest.mock import patch
import app
import text_list_builder as builder


class ParallelOrderTests(unittest.TestCase):
    def test_requested_note_and_inline_forms(self):
        text = """Criminal Minds (Season 6, Episodes 1-13)
Criminal Minds: Suspect Behavior (Season 1) *(Runs parallel to the rest of Criminal Minds Season 6)*
Criminal Minds (Season 6, Episodes 14-24)
Criminal Minds (Season 11) / Criminal Minds: Beyond Borders (Season 1) *(The International Response Team is introduced in Criminal Minds Season 10, Episode 19)*
Criminal Minds (Seasons 13-15)"""
        rows = builder.infer(text)
        self.assertNotIn("parallel_group", rows[0])
        self.assertEqual(rows[1]["parallel_lane"], 0)
        self.assertEqual(rows[2]["parallel_lane"], 1)
        self.assertEqual(rows[2]["episode"], "14")
        self.assertEqual(rows[3]["season"], "11")
        self.assertEqual(rows[4]["season"], "1")
        self.assertEqual(rows[3]["parallel_group"], rows[4]["parallel_group"])
        self.assertNotIn("parallel_group", rows[5])

    def test_markdown_names_and_ambiguous_note(self):
        rows = builder.infer(
            "[**Alpha**](https://example.com/alpha) (Season 2) / [**Beta**](https://example.com/beta) (Season 1)"
        )
        self.assertEqual([row["query"] for row in rows], ["Alpha", "Beta"])
        with self.assertRaisesRegex(ValueError, "explicit season/episode scope"):
            builder.infer("Alpha (Season 1) (runs parallel to Beta Season 2)")
        self.assertNotIn(
            "parallel_group",
            builder.infer("Parallel Universe (2010) (a parallel universe story)")[0],
        )

    def metadata(self, path, settings):
        parts = path.split("/")
        ident = parts[1]
        if len(parts) == 2:
            return {
                "id": int(ident),
                "name": "Show " + ident,
                "first_air_date": "2000-01-01",
            }
        count = 2 if ident == "1" else 3
        episodes = [
            {
                "id": 100 * int(ident) + n,
                "episode_number": n,
                "name": ident + "-" + str(n),
            }
            for n in range(1, count + 1)
        ]
        if len(parts) == 4:
            return {"id": 10 * int(ident), "name": "Season 1", "episodes": episodes}
        return next(e for e in episodes if e["episode_number"] == int(parts[-1]))

    def row(self, ident, lane):
        return {
            "confirmed": True,
            "type": "season",
            "tmdb": str(ident),
            "season": "1",
            "season_end": "1",
            "parallel_group": "parallel-1",
            "parallel_lane": lane,
        }

    def test_round_robin_keeps_tails_and_normal_following_entry(self):
        rows = [
            self.row(1, 0),
            self.row(2, 1),
            {"confirmed": True, "type": "movie", "tmdb": "3"},
        ]
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            result = builder.confirmed_items(rows, {}, app.normalize)
        self.assertEqual(
            [(r.get("show_tmdb"), r.get("episode")) for r in result[:-1]],
            [("1", "1"), ("2", "1"), ("1", "2"), ("2", "2"), ("2", "3")],
        )
        self.assertEqual(result[-1]["type"], "movie")
        self.assertEqual(len({r["id"] for r in result}), 6)

    def test_single_lane_and_noncontiguous_groups_rejected(self):
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            with self.assertRaisesRegex(ValueError, "at least two lanes"):
                builder.confirmed_items([self.row(1, 0)], {}, app.normalize)
            with self.assertRaisesRegex(ValueError, "contiguous"):
                builder.confirmed_items(
                    [
                        self.row(1, 0),
                        self.row(2, 1),
                        {"confirmed": True, "type": "movie", "tmdb": "3"},
                        self.row(1, 0),
                        self.row(2, 1),
                    ],
                    {},
                    app.normalize,
                )

    def test_partial_ranges_start_at_stated_episode(self):
        first = {
            **self.row(2, 0),
            "type": "episode",
            "episode": "2",
            "episode_end": "3",
        }
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            result = builder.confirmed_items([first, self.row(1, 1)], {}, app.normalize)
        self.assertEqual(
            [(r["show_tmdb"], r["episode"]) for r in result],
            [("2", "2"), ("1", "1"), ("2", "3"), ("1", "2")],
        )

    def test_multiple_seasons_stay_inside_their_lane(self):
        first = {**self.row(1, 0), "season_end": "2"}
        with patch("providers.cached_tmdb", side_effect=self.metadata):
            result = builder.confirmed_items([first, self.row(2, 1)], {}, app.normalize)
        self.assertEqual(
            [(r["show_tmdb"], r["season"], r["episode"]) for r in result],
            [
                ("1", "1", "1"),
                ("2", "1", "1"),
                ("1", "1", "2"),
                ("2", "1", "2"),
                ("1", "2", "1"),
                ("2", "1", "3"),
                ("1", "2", "2"),
            ],
        )

    def test_http_order_preview_has_no_state_writes(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch(
                "app.read_state", return_value={"settings": {"tmdb": {"key": "test"}}}
            ), patch("providers.cached_tmdb", side_effect=self.metadata), patch(
                "app.save_state"
            ) as save:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/lists/build/order-preview",
                    data=json.dumps(
                        {"items": [self.row(1, 0), self.row(2, 1)]}
                    ).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(request) as response:
                    result = json.load(response)
                self.assertEqual(result["count"], 5)
                self.assertEqual(
                    [row["show_tmdb"] for row in result["items"]],
                    ["1", "2", "1", "2", "2"],
                )
                save.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
