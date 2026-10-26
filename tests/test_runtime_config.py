# SPDX-License-Identifier: AGPL-3.0-only
"""Deployment behavior is tested without opening personal services."""
import os
import unittest
from unittest.mock import patch
import runtime_config
import app
import official_lists
import poster_overlays
from scripts import build_release, check_release


class RuntimeConfigTests(unittest.TestCase):
    def test_local_defaults_and_explicit_remote_host(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = runtime_config.server_options()
            self.assertEqual(cfg["host"], "127.0.0.1")
            self.assertNotIn("attacker.invalid", cfg["allowed_hosts"])
        with patch.dict(
            os.environ,
            {
                "LISTWEAVARR_HOST": "0.0.0.0",
                "LISTWEAVARR_PORT": "8766",
                "LISTWEAVARR_PUBLIC_URL": "https://lists.example.org",
                "LISTWEAVARR_ALLOWED_HOSTS": "nas.local:8766",
            },
            clear=True,
        ):
            cfg = runtime_config.server_options()
            self.assertIn("lists.example.org", cfg["allowed_hosts"])
            self.assertIn("nas.local:8766", cfg["allowed_hosts"])

    def test_unsafe_origins_and_wildcards_are_rejected(self):
        for value in (
            "file:///tmp",
            "https://user:secret@example.org",
            "https://example.org/path",
        ):
            with patch.dict(os.environ, {"LISTWEAVARR_PUBLIC_URL": value}, clear=True):
                with self.assertRaises(ValueError):
                    runtime_config.server_options()
        with patch.dict(os.environ, {"LISTWEAVARR_ALLOWED_HOSTS": "*"}, clear=True):
            with self.assertRaises(ValueError):
                runtime_config.server_options()

    def test_old_curator_setting_remains_compatible(self):
        with patch.dict(os.environ, {"REELCHECK_CURATOR_MODE": "1"}, clear=True):
            self.assertTrue(runtime_config.curator_enabled())
        with patch.dict(
            os.environ,
            {"LISTWEAVARR_CURATOR_MODE": "0", "REELCHECK_CURATOR_MODE": "1"},
            clear=True,
        ):
            self.assertFalse(runtime_config.curator_enabled())

    def test_runtime_archive_excludes_personal_material(self):
        paths = [
            p.relative_to(build_release.ROOT).as_posix()
            for p in build_release.source_files()
        ]
        self.assertIn("runtime_config.py", paths)
        self.assertIn("catalogue/bundled/official-lists.json", paths)
        self.assertFalse(check_release.validate_paths(paths))
        self.assertTrue(
            check_release.validate_paths(
                ["data/state.json", "audits/private.jpg", ".env"]
            )
        )

    def test_public_overlays_are_original_assets(self):
        from pathlib import Path

        with (
            patch.object(
                poster_overlays,
                "ASSETS",
                Path(__file__).resolve().parents[1] / "web/assets/overlays",
            ),
            patch(
                "providers.cached_tmdb",
                return_value={"status": "Ended", "networks": []},
            ),
        ):
            data = poster_overlays.show_info("1", {})
            self.assertEqual(data["status_asset"], "ended.svg")
            self.assertTrue(
                poster_overlays.asset_path(
                    "/poster-overlays/status-top-left/ended.svg"
                ).is_file()
            )
