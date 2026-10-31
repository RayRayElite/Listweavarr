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

    def test_preload_precedes_native_main_bundle(self):
        original = (
            b'<html><body><script src="js/main-fixture.js"></script></body></html>'
        )
        (self.root / "index.html").write_bytes(original)
        with patch.object(
            desktop, "KNOWN_INDEX", desktop.digest(original)
        ), patch.object(desktop, "plex_running", return_value=False):
            desktop.operate(self.root, "install")
            result = (self.root / "index.html").read_bytes()
            self.assertLess(
                result.index(b"listweavarr-playlist-layout.js"),
                result.index(b"js/main-fixture.js"),
            )
            desktop.operate(self.root, "uninstall")
        self.assertEqual((self.root / "index.html").read_bytes(), original)

    def test_update_migrates_old_asset_manifest_and_keeps_original_backup(self):
        import json

        with patch.object(desktop, "plex_running", return_value=False):
            desktop.operate(self.root, "install")
            state = json.loads((self.root / desktop.STATE).read_text())
            for name in (
                "listweavarr-playlist-layout.js",
                "listweavarr-playlist-artwork.js",
                "listweavarr-playlist-settings.js",
            ):
                state["assets"].pop(name)
                (self.root / name).unlink()
            old_index = self.original.replace(
                b"</body>",
                b'<script src="listweavarr-playlist-runtime.js"></script></body>',
            )
            (self.root / "index.html").write_bytes(old_index)
            state["patched_sha256"] = desktop.digest(old_index)
            (self.root / desktop.STATE).write_text(json.dumps(state))
            self.assertTrue(desktop.operate(self.root, "update")["updated"])
            self.assertEqual((self.root / desktop.BACKUP).read_bytes(), self.original)
            self.assertTrue((self.root / "listweavarr-playlist-artwork.js").exists())
            desktop.operate(self.root, "uninstall")
        self.assertEqual((self.root / "index.html").read_bytes(), self.original)

    def test_failed_update_restores_previous_working_install(self):
        with patch.object(desktop, "plex_running", return_value=False):
            desktop.operate(self.root, "install")
            before = {p.name: p.read_bytes() for p in self.root.iterdir()}
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder)
                for name in desktop.ASSETS:
                    (source / name).write_bytes(
                        (desktop.SOURCE / name).read_bytes() + b"\n/* new version */"
                    )
                write = desktop.atomic_write

                def fail_manifest(path, data):
                    if path.name == desktop.STATE:
                        raise PermissionError("simulated manifest failure")
                    write(path, data)

                with patch.object(desktop, "SOURCE", source), patch.object(
                    desktop, "atomic_write", side_effect=fail_manifest
                ):
                    with self.assertRaises(PermissionError):
                        desktop.operate(self.root, "update")
            self.assertEqual(
                {p.name: p.read_bytes() for p in self.root.iterdir()}, before
            )
            self.assertTrue(desktop.operate(self.root, "status")["installed"])

    def test_recover_preserves_new_unsupported_plex_index(self):
        with patch.object(desktop, "plex_running", return_value=False):
            desktop.operate(self.root, "install")
            new_index = b"<html><body>A new Plex version</body></html>"
            (self.root / "index.html").write_bytes(new_index)
            self.assertEqual(
                desktop.operate(self.root, "status")["status"], "needs-review"
            )
            result = desktop.operate(self.root, "recover")
        self.assertTrue(result["new_plex_index_preserved"])
        self.assertFalse(result["supported"])
        self.assertEqual((self.root / "index.html").read_bytes(), new_index)
        self.assertEqual([p.name for p in self.root.iterdir()], ["index.html"])

    def test_recover_refuses_to_remove_modified_owned_files(self):
        with patch.object(desktop, "plex_running", return_value=False):
            desktop.operate(self.root, "install")
            (self.root / "index.html").write_bytes(b"new clean Plex index")
            (self.root / "listweavarr-playlist-runtime.js").write_bytes(
                b"external edit"
            )
            with self.assertRaisesRegex(ValueError, "asset changed"):
                desktop.operate(self.root, "recover")
        self.assertTrue((self.root / desktop.BACKUP).exists())
