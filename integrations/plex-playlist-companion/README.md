# Playlist companion — development prototype

Desktop and web are both goals. This folder is deliberately independent of the
Listweavarr server: it currently needs no running Docker container or backend.
It is an experimental source-checkout component, not part of the runtime ZIP or
an installer intended for general distribution yet.

## Implemented

Development update: Plex Web 4.160.0's registered player services now have a
desktop adapter, with a small Playlist companion panel for Start, Resume and
Pause & save. Automatic checkpoints apply only to queues started/resumed through
this panel, not arbitrary playback elsewhere in Plex. The adapter validates
selected occurrence/offset against the full playlist before dispatching playback,
and preserves source ordering for mixed movies and episodes. It does not manually
mark items watched or edit playlists; Plex still records normal playback history.
On October 30, 2026, a live test with a 641-entry mixed playlist verified desktop
playback, pause/save and resume after restarting Plex near the saved 0:52 position.
The user confirmed the resumed point and playlist Up Next. This is one desktop
episode test, not complete cross-client or movie-playback certification. Poster
layout and the home row are not implemented.

- Shared offline bookmark rules: server/user/playlist separation, exact entry IDs,
  offsets, explicit completion, session revisions and reconciliation after edits.
  Global watched flags are not consulted. Duplicates whose entry IDs were lost
  need review rather than an assumed match.
- A version-checked Windows loader with exact original-file backup and rollback.
  It refuses running Plex, unknown entry-point hashes and changed installed files.
- A minimal Chrome/Edge extension development manifest for hosted Plex Web.
- The original bootstrap proved local-storage availability; the current desktop
  adapter additionally samples its bound player's progress every two seconds.
  Closing the client can lose the most recent interval. It does not yet infer
  final-item completion or automatically reassociate a queue after a restart.

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

The current console marker `[Listweavarr Playlist Companion] desktop player adapter
ready` reports that the version-specific services were found. It is not evidence
that playback succeeded. Hosted Web still has no verified player adapter and
disables its controls; the desktop adapter must not be assumed to support it.

## Next acceptance gates

1. Extend the passed desktop episode resume test to movies, actual queue advances,
   duplicate occurrences, rewatches and final-item completion. The adapter has no
   Listweavarr HTTP dependency; its bookmarks are local to the client.
2. Track playback started through normal Plex controls once its originating
   playlist can be established without guessing from shared titles.
3. Verify the hosted/local Plex Web adapters rather than assuming compatibility
   with this particular desktop bundle.
4. Add portrait video-playlist layout and Continue row in desktop and web adapters.
5. Add optional paired Listweavarr synchronization and artwork/update integration.

Tests: `node tests/test_playlist_bookmarks.cjs` from the repository root, plus the
desktop tests included in `python -m unittest discover -s tests -q`. Windows
installation checks use synthetic HTML in tests, not redistributed Plex code.
