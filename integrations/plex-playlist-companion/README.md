# Listweavarr Playlist Companion 0.4

Optional enhancements for Plex for Windows and Plex Web. Playback bookmarks and
cached artwork stay on the Plex device. Listweavarr does **not** need to run for
playlist tracking or resume; it runs only when you want new artwork imported.
This is a beta, version-specific integration. Plex app updates can require a
compatibility update. No Plex source, executable or artwork is included here.

## What it does

- Continue Playlists appears after Plex's complete Continue Watching row.
- Normal playlist Play and starting at a middle entry create a resume card.
- Saves during playback, on Stop/Pause and orderly window close. Completion
  advances the bookmark to the next item; finished playlists leave the row.
- Native playlist cards use a portrait metric shared by cards and virtualized
  rows, rather than stretching images inside square rows.
- A pencil appears on poster hover/focus for an explicit device-local poster.
- Optional Listweavarr artwork pairing imports portrait list posters, updates
  changed images and caches them locally. Local pencil choices take priority.
- A small settings gear replaces development controls. Diagnostics are available
  inside settings, with no floating development button during normal use.

Bookmarks use server, Plex user, playlist and exact playlist-entry identity.
Duplicate title occurrences remain separate. Ordinary playback outside a verified
playlist never creates a playlist bookmark. The companion does not manually mark
anything watched, alter playlist order or request downloads. Plex records its
normal playback history when you play media.

## Supported client builds

| Client | Build inspected |
| --- | --- |
| Plex for Windows | 1.115.0.426-4e960a1d / embedded Web 4.160.0-75ddd7b |
| Local NAS Plex Web | 4.147.1-4ca0656 |
| Hosted Plex Web | 4.163.0-8246fd2 |

These are exact main-bundle allowlist entries in layout.js. Unknown builds are
left unchanged. Desktop native Play, middle-entry starts, correct queue ordering,
Stop/Pause and Home resume have passed live user tests. Episode rollover followed
by closing Plex without Stop/Pause also preserved the next item. New portrait
layout, artwork pairing and browser playback still need the current live review;
source contracts and shared metrics were checked against all three real bundles.
Movie/final-item completion, modified queues and duplicate occurrences also have
automated checks; broader client certification remains separate from those tests.

## Windows installation

1. Extract the standalone companion ZIP, or open this source folder.
2. Install Python 3.11 or newer if it is not already installed. Close Plex.
3. Run **Setup Playlist Companion.cmd** and choose **Install / update**. Windows
   requests administrator access because Plex lives in Program Files.
4. Start Plex. Use its ordinary playlist Play controls; the diagnostics panel is
   not required. Existing bookmarks and local posters survive companion updates.

Command-line alternatives:

```powershell
python desktop.py status
python desktop.py update
python desktop.py uninstall
```

Use `--web-client` for a different installed web-client directory. The installer
verifies the original index and every owned asset, retains an exact original-file
backup and rolls back a failed update. It refuses running Plex, symlinks, unknown
client versions and externally changed companion files.

If Plex itself updates, run Status first. If the new index is clean but verified
old companion assets remain, **Recover after Plex update** removes only those old
assets and preserves Plex's new index. It never restores an older index over a new
Plex release. Unknown releases need an updated companion before reinstalling.
Uninstall on a supported intact install restores the byte-identical original.
Setup results are also available in the Windows temporary directory as
`Listweavarr-Playlist-Companion-setup.log`.

## Chrome / Edge installation

1. Extract the **Chrome** companion ZIP, or run `python scripts/build_playlist_companion.py`
   from the repository root and use `releases/Playlist-Companion-Chrome`.
   Open the browser's Extensions page, enable Developer mode, then **Load unpacked**
   and select that browser-only folder. Do not select the Python source folder:
   Python can create a `__pycache__` directory there, which Chrome rejects.
2. Reload hosted Plex Web at `https://app.plex.tv/desktop/`.
3. For your NAS's Plex Web, open this extension's Options page and enter the
   server origin, for example `https://your-plex-server:32400/web/`. Approve access
   to that server, then reload its Plex Web tab.

The extension runs original packaged scripts in Plex's page world so they can use
its existing player. Hosted Plex access is limited to /desktop/. Local origins
are opt-in, registered only for /web/, and removable from Options. It does not
request browsing history or access to every website. Bookmarks are per origin and
browser profile; desktop and browser bookmarks are not synchronized yet.

## Optional automatic Listweavarr artwork

1. In Listweavarr, go to Settings > Connections > Plex playlist companion.
2. Create an artwork pairing. Existing playlists can be recognized by their exact
   ordered Plex IDs; ambiguous matches are skipped. Names alone never count.
3. Copy the pairing into Plex Home > Continue Playlists gear > artwork pairing,
   and choose Connect / refresh artwork. Repeat on another device using the same
   pairing if desired. Creating another pairing revokes the previous one.
4. The companion checks for changed artwork at startup and every five minutes.
   Closing Listweavarr leaves existing cached posters and bookmarks usable.

The pairing is revocable and read-only, scoped to mapped artwork. It never exposes
Plex tokens, list entries, account information or watched history. Artwork-only
associations do not grant Listweavarr authority to replace or delete a playlist.
The normal portrait poster is preferred; a square playlist poster is a fallback.
Other Plex clients keep their existing selected posters. An explicit pencil choice
is never automatically overwritten. Disconnecting or revoking a pairing keeps
cached images. For hosted HTTPS Plex Web, use a Listweavarr address the browser
permits (HTTPS or an allowed localhost address); do not bypass browser security
warnings. The app supports the paired Plex origin, hosted Plex, native file origin
and the configured Plex Direct LAN address for artwork CORS, not arbitrary sites.

## Development and verification

### Optional cross-device progress sync

Create a fresh pairing in Listweavarr Settings > Connections > Playlist companion.
Paste the same pairing into the companion settings in Windows Plex and Plex Web,
then enable **Sync playlist progress between paired devices** on both clients.
Existing local bookmarks upload automatically; no restart of a playlist is needed.
Posters chosen with the companion pencil also migrate, including legacy desktop
choices. Artwork sync runs at startup, on Connect / refresh artwork and every five
minutes. Explicit local choices stay pinned on that client; imported shared images
can refresh. Shared image files stay in the private data/companion-posters folder.
Keep the Listweavarr service running and reachable from each device for syncing.
Clients exchange bookmarks every ten seconds while Plex is open. Offline playback
continues saving locally and syncs when connectivity returns. The latest playback
timestamp wins; devices should have correct system clocks. A sudden close can
lose up to one sync interval remotely, but the local checkpoint remains available.

Progress uses a separate write capability from the read-only artwork token.
Treat the pairing as private: it grants access to companion bookmarks on this
Listweavarr instance. Revoking/rotating it disables both capabilities without
deleting local bookmarks. User/server/playlist keys separate stored progress;
this single-user service does not implement independent household authentication.
Plex watched flags and watch history are never modified by syncing.

```powershell
node tests/test_playlist_bookmarks.cjs
node tests/test_playlist_adapter.cjs
node tests/test_playlist_features.cjs
node tests/test_playlist_sync.cjs
node tests/test_playlist_poster_sync.cjs
node tests/test_playlist_home.cjs
python -m unittest discover -s tests -q
python scripts/build_playlist_companion.py
```

The builder includes only an explicit list of original companion files and the
AGPLv3 license. It excludes installed Plex bundles, private data, logs and images.
The main Listweavarr Docker container does not patch Plex on another machine;
install this client-side companion separately on the device/browser using Plex.

Power loss can still lose writes the operating system has not flushed. Checkpoint
writes happen during playback, so orderly Stop is not required. Completion uses
the final reported second of a known duration; errors or unknown durations never
imply completion. Changed or ambiguous playlist identities require review rather
than guessing by title or using global watched flags.
