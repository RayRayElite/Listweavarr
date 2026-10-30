# Plex playlist enhancement investigation

Investigated October 30, 2026. This is a feasibility report and proposed design,
not an installed patch or a demonstrated playback integration.

## Recommended direction

Build a Listweavarr playlist-progress service and a companion Plex Web extension.
Use a separate, optional desktop adapter if the installed Plex for Windows client
can be modified safely and reversibly. Keep one shared implementation of progress
and resume rules so the clients do not become independent products.

The intended experience is a **Continue your playlists** home row: portrait
collection artwork, playlist name, current episode/movie, position in the list,
and a Resume action. Include this in Listweavarr as a fallback as well as the
enhanced Plex Web home page. Starting from a playlist should opt it into tracking;
offer a visible stop-tracking action and manual bookmark correction.

The user's requested poster-like shape is interpreted here as width:height 2:3,
the portrait ratio found in the installed client's layout code. Literal 2:1 would
be landscape, and needs confirmation if that was intended.

## What was inspected

- Local installation: `C:\Program Files\Plex\Plex`.
- Contains Qt/QtWebEngine libraries and an extracted `web-client` directory;
  bundled web assets identify themselves as Plex Web 4.160.0.
- REA inspected the installation and statically parsed the `chunk-4276` bundle.
  Its graph coverage was partial and reached semantic retention limits. It did
  not execute Plex, prove a runtime route, or establish that injection works.
- Bounded inspection of the other installed bundles found playlist-item models,
  playlist-entry identifiers, play-queue identifiers/selection, and layout
  calculations that use aspect ratio when calculating cell height.
- The playlist view bundle includes a virtualized grid. Changing only image CSS
  is therefore insufficient evidence of a correct layout: row sizes, image
  requests, focus/hover regions and scroll calculations must agree.
- No installed Plex files, authentication settings, playlists, watch flags or
  playback sessions were changed. Private file hashes and REA evidence IDs are
  retained in `data/plex-playlist-research/evidence-manifest.json`. No Plex client
  bundle is included in Listweavarr's repository.

These observations make a common web enhancement plausible. They do not establish
that current hosted Plex Web uses the same version or internals as this desktop
installation. Plex HTPC, mobile and TV apps are separate compatibility targets.

## Supported APIs and client-specific work

The [Plex Media Server API](https://developer.plex.tv/pms/) documents playlist
contents and explicit `playlistItemID` values for ordinary playlists. It also
documents play queues created from a playlist, with an initial item key and
shuffle disabled. This supplies useful building blocks, not a persistent
playlist-bookmark contract. Plex describes play queues as ephemeral session
state; queue selection offsets must not be confused with playback milliseconds.

Changing Plex's card shape and inserting a custom home row require client UI
integration. The old server plug-in mechanism is not a general client UI
extension system; see Plex's [plug-in overview](https://support.plex.tv/articles/201053748-overview/).
No documented custom Plex home-row installation API was established in this
investigation. Do not present a backend-only feature as changing every Plex app.

| Surface | Proposed integration | Main uncertainty |
| --- | --- | --- |
| Plex Web in Chrome/Edge | Optional extension: playlist cards, tracking controls and home row | Hosted and local Plex versions, virtualized layout and playback adapter |
| Listweavarr | Persistent progress, artwork and a matching resume row | Plex client handoff must preserve queue and offset |
| Native Plex for Windows | Optional original-code loader targeting an explicitly supported installed web bundle | Asset loading, CSP, client bridge, updates and reversible installation |
| Other Plex apps | Server-observed progress where playlist context can be established | No custom home UI; shared titles alone do not identify the active playlist |

## Progress model

Persist a bookmark separately from global watched status. A previously watched
episode can still be the next item during a chronological rewatch.

Key progress by Plex server, Plex user/profile, playlist and entry occurrence.
Retain the playlist entry ID, rating key, duplicate-occurrence discriminator,
position hint, playback offset in milliseconds, duration, completion state,
last-activity time, playlist revision/fingerprint and session/client binding.
Entry position alone is not stable when the list is edited. Rating key alone is
not sufficient when a title appears more than once.

Record playlist context at an explicit Start/Resume or playlist Play action,
then associate actual playback updates with that session. Advance after observed
completion or the next queue item, not simply because a title is globally watched.
Handle seeking, manual skipping, credits, pausing, stopping, replaying and multiple
concurrent sessions explicitly. Completion should respect Plex completion evidence
where available; do not hard-code a universal percentage without validation.

Server sessions/notifications can complement client observations. They must not
attribute unrelated playback to every playlist containing the same movie/episode.
For playback launched on unmodified clients, use confirmed playlist/queue context
where available; otherwise ask for association or retain the last known bookmark.
Polling may miss short sessions; do not promise lossless universal tracking.

When playlists update, reconcile by stable entry ID first, then an unambiguous
item/occurrence match. If an entry was removed or recreated ambiguously, display
that fact and offer a new position. Do not silently reset or skip new content.
Begin with ordinary video playlists; smart playlists require separate handling.

## Resume contract

1. Resolve the saved playlist entry against current server contents.
2. Build or request the playlist queue in source order, starting at that entry.
3. Ask the selected Plex client to play the queue at the saved playback timestamp.
4. Verify that the intended item, offset and following item are active.

Creating a server queue alone does not start client playback. Opening a title
detail URL does not satisfy this contract. Desktop deep links and browser-player
actions must each be tested. Duplicate occurrences require a client adapter that
selects the intended occurrence; an initial metadata key alone may be ambiguous.
Any fallback that only opens details must be labelled as such.

## Artwork and layout

Use the existing portrait list artwork for enhanced video-playlist cards. Retain
the separate square playlist artwork for ordinary Plex clients. A portrait asset
uploaded to Plex does not by itself change the client's card dimensions.

Change only video-playlist presentation, leaving audio playlists alone. Update
image containers, requests, grid metrics, captions, selection and action overlays
together. Test narrow/wide windows, zoom, long names, missing artwork, keyboard
navigation and virtualized scrolling. Avoid brittle dependence on one hashed CSS
class or forced global image stretching.

## Distribution and access

The extension should request only the chosen Plex origins and the configured
Listweavarr service. Use explicit local pairing and scoped credentials; do not
embed Plex account tokens in public scripts, share URLs or extension source.
Keep server credentials on the backend where possible. A website must not be
able to trigger local playback/control merely by reaching a loopback endpoint:
validate pairing, origin and request intent. HTTPS Plex to a local HTTP service
also needs an extension messaging/network design rather than assuming page fetch
will work through browser restrictions.

For a native desktop adapter, distribute our own integration code, not a modified
copy of Plex. Before any patch, verify a supported client version and file hashes,
make a backup, require the app to be closed and provide rollback. Unknown versions
should disable the adapter. Test upgrades, CSP, security software behavior and
repair/uninstall. A Qt client cannot simply load a Chrome extension.

## Implementation order and acceptance gates

1. Read-only playback experiment on a deliberately selected test playlist:
   observe entry, queue and timestamp behavior without changing watched status.
2. Bookmark service with tests for rewatches, duplicates, reordered/deleted entries,
   restarts, separate users, concurrent sessions and unavailable media.
3. Plex Web extension prototype: portrait video-playlist cards plus Continue row.
   Resume must pass the full queue/item/timestamp contract before public release.
4. Desktop proof of concept on a backed-up, version-checked installation. Confirm
   the actual asset-loading path before designing an installer.
5. Package the extension and optional adapter with a compatibility matrix and
   rollback instructions; validate a Plex update before expanding support.

This investigation establishes a practical direction, not a guarantee that both
Plex surfaces can be supported with one patch. The backend and browser route are
the first deliverables; native desktop support remains a separate test gate.
