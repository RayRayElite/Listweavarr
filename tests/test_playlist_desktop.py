# SPDX-License-Identifier: AGPL-3.0-only
"""Rollback checks use synthetic HTML, never copy Plex's proprietary bundle."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "playlist_desktop",
    Path(__file__).resolve().parents[1]
    / "integrations/plex-playlist-companion/desktop.py",
)
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = b"<html><body>Fixture</body></html>"
        (self.root / "index.html").write_bytes(self.original)
        self.hash = patch.object(desktop, "KNOWN_INDEX", desktop.digest(self.original))
        self.hash.start()
        self.addCleanup(self.hash.stop)

    def test_install_is_idempotent_and_uninstall_restores_exact_bytes(self):
        with patch.object(desktop, "plex_running", return_value=False):
            self.assertTrue(desktop.operate(self.root, "install")["backup_verified"])
            self.assertFalse(desktop.operate(self.root, "install")["changed"])
            self.assertTrue(
                desktop.operate(self.root, "uninstall")["restored_original"]
            )
        self.assertEqual((self.root / "index.html").read_bytes(), self.original)
        self.assertEqual([p.name for p in self.root.iterdir()], ["index.html"])

    def test_busy_or_unknown_client_is_untouched(self):
        with patch.object(desktop, "plex_running", return_value=True):
            with self.assertRaisesRegex(ValueError, "Close Plex"):
                desktop.operate(self.root, "install")
        (self.root / "index.html").write_bytes(b"new version")
        with patch.object(desktop, "plex_running", return_value=False):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                desktop.operate(self.root, "install")
        self.assertEqual([p.name for p in self.root.iterdir()], ["index.html"])

    def test_update_or_modified_asset_is_not_overwritten(self):
        with patch.object(desktop, "plex_running", return_value=False):
            desktop.operate(self.root, "install")
            (self.root / "listweavarr-playlist-runtime.js").write_bytes(
                b"external change"
            )
            with self.assertRaisesRegex(ValueError, "asset changed"):
                desktop.operate(self.root, "uninstall")
        self.assertTrue((self.root / desktop.BACKUP).exists())

    def test_partial_install_failure_leaves_original_entry_point(self):
        write = desktop.atomic_write

        def fail_asset(path, data):
            if path.name == "listweavarr-playlist-runtime.js":
                raise PermissionError("simulated write failure")
            write(path, data)

        with patch.object(desktop, "plex_running", return_value=False), patch.object(
            desktop, "atomic_write", side_effect=fail_asset
        ):
            with self.assertRaises(PermissionError):
                desktop.operate(self.root, "install")
        self.assertEqual((self.root / "index.html").read_bytes(), self.original)
        self.assertEqual([p.name for p in self.root.iterdir()], ["index.html"])
