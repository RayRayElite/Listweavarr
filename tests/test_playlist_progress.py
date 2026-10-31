# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
import playlist_progress as progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(serverId="server", userId="alice", playlistId="7")
        self.row = dict(
            self.scope,
            schema=1,
            entryId="8",
            ratingKey="9",
            sessionId="session",
            offsetMs=100,
            revision=1,
            updatedAt=1000,
            ratingKeyOccurrences=1,
            completed=False,
        )
        self.state = {
            "playlist_artwork_pairing": {"machine": "server", "token": "art"},
            "playlist_progress_token": "progress",
        }

    def exchange(self, rows):
        return progress.merge(self.state, {"scopes": [self.scope], "items": rows})[
            "items"
        ]

    def test_migration_newer_wins_and_retries_are_idempotent(self):
        self.assertEqual(self.exchange([self.row]), [self.row])
        newer = dict(self.row, updatedAt=2000, offsetMs=500)
        self.exchange([newer])
        self.assertEqual(self.exchange([self.row]), [newer])
        self.assertEqual(self.exchange([newer]), [newer])

    def test_profiles_are_separate(self):
        self.exchange([self.row])
        self.scope = dict(self.scope, userId="bob")
        self.assertEqual(self.exchange([]), [])

    def test_wrong_server_or_invalid_batch_cannot_write(self):
        for invalid in (
            dict(self.row, serverId="other"),
            dict(self.row, updatedAt=9999999999999),
            dict(self.row, offsetMs=-1),
        ):
            before = copy.deepcopy(self.state)
            with self.assertRaises(ValueError):
                self.exchange([self.row, invalid])
            self.assertEqual(self.state, before)

    def test_artwork_token_does_not_grant_write_access(self):
        self.assertFalse(progress.authorize(self.state, "Bearer art"))
        self.assertTrue(progress.authorize(self.state, "Bearer progress"))
        self.state.pop("playlist_progress_token")
        self.assertFalse(progress.authorize(self.state, "Bearer progress"))


if __name__ == "__main__":
    unittest.main()
