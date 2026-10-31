# SPDX-License-Identifier: AGPL-3.0-only
"""Managed publication reads detect drift before any Plex mutation."""
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import app
import plex_publications


class PublicationTests(unittest.TestCase):
    def test_fully_covered_season_yields_to_explicit_episode_order(self):
        plan = app.playlist_preview(
            {
                "name": "Interleaved",
                "items": [
                    {
                        "title": "Season",
                        "type": "season",
                        "status": "available",
                        "plex_keys": ["1", "2"],
                    },
                    {
                        "title": "Second first",
                        "type": "episode",
                        "status": "available",
                        "plex_keys": ["2"],
                    },
                    {
                        "title": "Other show",
                        "type": "episode",
                        "status": "available",
                        "plex_keys": ["3"],
                    },
                    {
                        "title": "First last",
                        "type": "episode",
                        "status": "available",
                        "plex_keys": ["1"],
                    },
                ],
            }
        )
        self.assertEqual(plan["keys"], ["2", "3", "1"])
        self.assertEqual(plan["duplicate_count"], 0)
        self.assertEqual(plan["covered_seasons"], 1)
        self.assertEqual(plan["omitted"], 0)
        self.assertIn("individual episode", plan["entries"][0]["detail"])

    def test_partially_covered_season_is_not_silently_discarded(self):
        plan = app.playlist_preview(
            {
                "name": "Incomplete",
                "items": [
                    {
                        "title": "Season",
                        "type": "season",
                        "status": "available",
                        "plex_keys": ["1", "2"],
                    },
                    {
                        "title": "Only first",
                        "type": "episode",
                        "status": "available",
                        "plex_keys": ["1"],
                    },
                ],
            }
        )
        self.assertEqual(plan["keys"], ["1", "2", "1"])
        self.assertEqual(plan["covered_seasons"], 0)
        self.assertEqual(plan["duplicate_count"], 1)

    def test_overlap_preview_identifies_whole_season_and_episode_rows(self):
        plan = app.playlist_preview(
            {
                "name": "Mixed order",
                "items": [
                    {
                        "title": "Season 5",
                        "status": "available",
                        "plex_keys": ["1", "2"],
                    },
                    {"title": "Episode one", "status": "available", "plex_keys": ["1"]},
                    {"title": "Episode two", "status": "available", "plex_keys": ["2"]},
                ],
            }
        )
        self.assertEqual(plan["duplicate_count"], 2)
        self.assertEqual(
            plan["overlaps"],
            [
                {
                    "position": 1,
                    "title": "Season 5",
                    "count": 2,
                    "with_positions": [2, 3],
                }
            ],
        )
        self.assertEqual(plan["keys"], ["1", "2", "1", "2"])

    def test_duplicate_playable_scopes_fail_before_creating_a_playlist(self):
        rows = [
            {"status": "available", "plex_keys": ["1", "2"]},
            {"status": "available", "plex_keys": ["1"]},
        ]
        with patch("app.compare", return_value=rows), patch("app.remote") as remote:
            with self.assertRaisesRegex(ValueError, "1 repeated Plex items"):
                app.create_playlist(
                    {"name": "Overlapping list", "items": rows},
                    {"plex": {"url": "http://nas", "key": "private"}},
                    "Overlapping list",
                )
        remote.assert_not_called()

    def test_remote_drift_preserves_old_target_before_deletion(self):
        entry = {
            "name": "List",
            "items": [],
            "playlist": {"key": "5", "server": "http://nas", "title": "Saved"},
        }
        rows = [{"status": "available", "plex_keys": ["1"]}]
        expected = {
            "desired_fingerprint": app.playlist_preview(
                {"name": "List", "items": rows}
            )["fingerprint"],
            "target": {"key": "5", "keys": ["2"]},
        }
        responses = [
            ET.fromstring('<MediaContainer><Playlist title="Saved"/></MediaContainer>'),
            ET.fromstring('<MediaContainer machineIdentifier="machine"/>'),
            ET.fromstring('<MediaContainer><Playlist ratingKey="6"/></MediaContainer>'),
            ET.fromstring('<MediaContainer><Video ratingKey="1"/></MediaContainer>'),
        ]
        with patch("app.compare", return_value=rows), patch(
            "app.remote", side_effect=responses
        ) as remote, patch(
            "app.plex_publications.target",
            side_effect=[expected["target"], {"key": "5", "keys": ["external-edit"]}],
        ):
            with self.assertRaisesRegex(ValueError, "Both playlists were preserved"):
                app.create_playlist(
                    entry,
                    {"plex": {"url": "http://nas", "key": "secret"}},
                    "Saved",
                    True,
                    expected=expected,
                    guard=lambda: None,
                )
        self.assertFalse(
            any(call.kwargs.get("method") == "DELETE" for call in remote.call_args_list)
        )

    def test_diff_counts_occurrences_and_relative_order(self):
        result = plex_publications.changes(["1", "1", "2"], ["2", "1", "3"])
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["removed"], 1)
        self.assertTrue(result["reordered"])
        self.assertFalse(
            plex_publications.changes(["1", "2"], ["0", "1", "2"])["reordered"]
        )

    def test_unowned_targets_and_incomplete_reads_are_rejected(self):
        settings = {"plex": {"url": "http://nas", "key": "secret"}}
        with self.assertRaises(ValueError):
            plex_publications.target({}, settings, lambda *a, **k: None)
        entry = {"playlist": {"key": "5", "server": "http://nas", "title": "Saved"}}
        responses = [
            ET.fromstring('<MediaContainer machineIdentifier="machine"/>'),
            ET.fromstring('<MediaContainer><Playlist title="Saved"/></MediaContainer>'),
            ET.fromstring('<MediaContainer totalSize="1"/>'),
        ]
        with patch("app.remote", side_effect=responses) as remote:
            with self.assertRaisesRegex(ValueError, "incomplete"):
                plex_publications.target(entry, settings, remote)

    def test_availability_drift_prevents_creation(self):
        entry = {"name": "List", "items": []}
        with patch(
            "app.compare", return_value=[{"status": "available", "plex_keys": ["1"]}]
        ), patch("app.remote") as remote:
            with self.assertRaisesRegex(ValueError, "changed after preview"):
                app.create_playlist(
                    entry,
                    {"plex": {"url": "http://nas", "key": "secret"}},
                    "List",
                    expected={"desired_fingerprint": "stale"},
                )
        remote.assert_not_called()
