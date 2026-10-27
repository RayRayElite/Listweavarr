# SPDX-License-Identifier: AGPL-3.0-only
"""Managed publication reads detect drift before any Plex mutation."""
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import app
import plex_publications


class PublicationTests(unittest.TestCase):
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
