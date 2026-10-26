# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import providers
import request_ledger


class RequestArtwork(unittest.TestCase):
    def test_public_queue_uses_cached_art_without_network_or_state_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            (cache / "tmdb").mkdir()
            key = hashlib.sha256(b"tv/42").hexdigest() + ".json"
            (cache / "tmdb" / key).write_text(
                json.dumps({"poster_path": "/poster.jpg"})
            )
            state = {
                "requests": [
                    {
                        "id": "one",
                        "item": {
                            "type": "episode",
                            "show_tmdb": "42",
                            "title": "Episode",
                        },
                    }
                ]
            }
            with (
                patch.object(providers, "CACHE", cache),
                patch.object(
                    providers,
                    "tmdb",
                    side_effect=AssertionError("Queue must not fetch metadata"),
                ),
            ):
                result = request_ledger.public(state)
            self.assertEqual(
                result["items"][0]["item"]["poster"],
                "https://image.tmdb.org/t/p/w342/poster.jpg",
            )
            self.assertNotIn("poster", state["requests"][0]["item"])

    def test_missing_or_damaged_cache_does_not_break_queue(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(providers, "CACHE", Path(folder)),
        ):
            self.assertEqual(providers.peek_tmdb("movie/42"), {})
            (Path(folder) / "tmdb").mkdir()
            key = hashlib.sha256(b"movie/42").hexdigest() + ".json"
            (Path(folder) / "tmdb" / key).write_text("{broken")
            self.assertEqual(providers.peek_tmdb("movie/42"), {})
