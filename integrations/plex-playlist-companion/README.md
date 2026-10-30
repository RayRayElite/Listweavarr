# Playlist companion — development prototype

Desktop and web are both goals. This folder is deliberately independent of the
Listweavarr server: it currently needs no running Docker container or backend.
It is an experimental source-checkout component, not part of the runtime ZIP or
an installer intended for general distribution yet.

## Implemented

- Shared offline bookmark rules: server/user/playlist separation, exact entry IDs,
  offsets, explicit completion, session revisions and reconciliation after edits.
  Global watched flags are not consulted. Duplicates whose entry IDs were lost
  need review rather than an assumed match.
- A version-checked Windows loader with exact original-file backup and rollback.
  It refuses running Plex, unknown entry-point hashes and changed installed files.
- A minimal Chrome/Edge extension development manifest for hosted Plex Web.
- A bootstrap probe reporting local-storage availability. It does not save real
  playback bookmarks, observe Plex events, change card layouts or control playback.

## Desktop probe

The tested entry-point hash is from Plex for Windows 1.115.0.426-4e960a1d,
bundled web client 4.160.0. Other versions are intentionally not admitted yet.
Plex's own startup log confirmed the local HTML entry point; the installed probe
then emitted a bootstrap marker with `platform: desktop` and available storage.
That verifies script loading, not a working playlist UI or resume adapter.

From this folder:

```powershell
python desktop.py status
# Close Plex first; Program Files writes usually require an elevated terminal.
python desktop.py install
python desktop.py uninstall
```

Use `--web-client` for a different installation path. Uninstall restores the
byte-identical saved index and removes only the verified companion-owned files.
If Plex has updated or another tool changed those files, stop and inspect instead
of overwriting. The development installer does not close Plex or elevate itself.
No native executable, media file, Plex database or watched state is modified.

## Browser probe

In Chrome/Edge's extension development screen, load this folder unpacked, then
reload hosted Plex Web. The extension has no backend connection and requests no
general browsing/history permissions. Its JavaScript runs in the extension's
isolated world; a future page/player bridge must be explicit and narrowly scoped.
Local server Plex Web origins are not enabled in this first manifest.

The console marker `[Listweavarr Playlist Companion] bootstrap` reports the
platform and storage availability. The exposed diagnostics explicitly state that
automatic tracking, poster layout and resume are disabled.

## Next acceptance gates

1. Observe an explicitly selected playlist's playback context in the desktop client.
2. Bind queue entries and timestamps to that context; persist a real checkpoint
   and verify it survives closing/reopening Plex without Listweavarr running.
3. Resume the intended item at its timestamp with the correct following queue.
   Test duplicates and rewatches; opening a title page is not success.
4. Add portrait video-playlist layout and Continue row in desktop and web adapters.
5. Add optional paired Listweavarr synchronization and artwork/update integration.

Tests: `node tests/test_playlist_bookmarks.cjs` from the repository root, plus the
desktop tests included in `python -m unittest discover -s tests -q`. Windows
installation checks use synthetic HTML in tests, not redistributed Plex code.
