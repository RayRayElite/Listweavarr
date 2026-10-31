# Playlist Companion beyond Windows and Web

Research date: October 31, 2026. Research and proposed architecture only; no TV,
console, server routing or playback settings were changed for this investigation.

## Recommendation

Build an optional **server-connected Playlist Companion service**, sharing the
bookmark and artwork implementation we already have. Keep Windows/Web adapters
for the richer native Home experience. For TVs and consoles, first test resuming
through the **unmodified Plex app**, rather than porting our desktop patch.

This can make playlist progress portable without a patch for every device.
It cannot, through the documented server controls reviewed here, force every Plex
app to display our portrait playlist cards, edit controls or Continue Playlists
row. Those are separate client presentation features.

Our Windows/Web work already demonstrates shared bookmarks and artwork. A
background observer of playback from unmodified clients, remote TV handoff and
managed continuation playlists are **proposals**, not working features yet.

## What belongs on the server side

The [Plex Media Server API](https://developer.plex.tv/pms/) provides playlist and
play-queue building blocks. A persistent playlist bookmark remains our own data:
server, user, playlist, exact entry occurrence and playback timestamp. A temporary
play queue is not a replacement for that bookmark.

The service should:

- Reuse existing bookmark reconciliation, custom posters and per-user isolation.
- Associate playback with a verified playlist/queue, then observe sessions and
  save periodic checkpoints, pause/stop and transitions to the next entry.
- Preserve duplicate entries, rewatches and curated ordering across list updates.
- Expose Resume on device and a clear fallback when a receiver is unavailable.
- Keep the source playlist unchanged; manage only explicitly created targets.

[Plex webhooks](https://support.plex.tv/articles/115002267687-webhooks/) offer
playback events and require a server-owner Plex Pass. Their documented payload
identifies the account, server, player and media; it does not establish a reliable
playlist-occurrence identity. Use events as signals, with session/queue inspection
and polling where needed. Do not require webhooks for the basic design.

**Important identity constraint:** seeing Being John Malkovich playing does not
prove MindFuck Collection was started. The same title might be played directly,
from another list, or appear twice in one list. Without verified context, leave
the playlist bookmark unchanged or offer explicit association. Do not guess.

For passive tracking while someone watches on a TV, this service must be running.
Docker beside Plex is convenient, but a Windows background process or NAS service
also works. It need not be embedded in, or modify, Plex Media Server. If it is
offline, native Plex still works; cross-device checkpoints may be missed. Retain
the existing clients' offline bookmarks and sync when available.

## Ways to use ordinary Plex clients

### 1. Resume on a selected device — preferred first prototype

Open Listweavarr on a phone/computer, choose a playlist and a running Plex receiver,
and send playback starting at the saved entry/time with the correct following
items. Watch in the normal TV app; the service tracks that associated session.

Plex lists Fire TV, Xbox, supported Smart TVs, Android TV, Apple TV and Roku as
[Companion receivers](https://support.plex.tv/articles/203082707-supported-plex-companion-apps/).
That is promising capability evidence, **not proof our handoff works on each
current app**. Discovery, permissions, local connectivity and queue commands need
real-device tests. The article also excludes newer mobile apps from its scope.

The maintained [Python PlexAPI client implementation](https://python-plexapi.readthedocs.io/en/stable/_modules/plexapi/client.html)
distinguishes modern createPlayQueue control from legacy playMedia. We should
probe actual receiver capabilities rather than ship one legacy command for all.
Creating a queue on the server alone does not start playback on a TV.

Trade-off: an extra phone/computer interaction, but no modified TV installation.

### 2. Managed continuation playlists — native navigation fallback

Maintain a separate playlist such as **Continue — MCU Extended**, containing the
saved current entry followed by the remaining entries in order. Its first item
moves forward as progress advances. It uses normal Plex playlist navigation and
can carry our artwork, subject to the app's own square/portrait presentation.

This avoids scrolling through hundreds of entries and may be the broadest usable
fallback. However, native playlist Play may start the first item at zero or use
Plex's global media resume offset. **Exact playlist-specific timestamp resume is
unproven here.** Test it before describing this option as equivalent to our
Windows/Web Resume action.

Keep generated lists per user, map generated occurrences back to their source,
and refresh after a session settles. Do not rewrite an active play queue or trim
the original list. Provide stop managing/delete generated copy controls. Users
should opt in because these copies add entries to their Plex playlist library.

### 3. Native Home recommendations — useful, limited

[Manage Recommendations](https://support.plex.tv/articles/manage-recommendations/)
controls library recommendation rows, subject to pinned sources and client
caching. Test whether a native Playlists row makes continuation copies convenient
on each target. It is not a documented arbitrary custom-row API.

[Published collections](https://support.plex.tv/articles/publishing-collections/)
can produce Home rows and require the server admin's Plex Pass. They expose
collection contents, not our custom playlist bookmark cards. Library collections
also do not replace one ordered, mixed movie/episode playlist spanning libraries.
Do not promise our exact Continue Playlists UI through collection publishing.

## Device feasibility

These are engineering assessments, not tested support claims.

| Device | First route | Rich custom interface | Assessment |
| --- | --- | --- | --- |
| Xbox Plex app | Existing receiver + service; continuation copy fallback | Separate Xbox application, not our Windows loader | Good candidate for an unmodified-client experiment; high effort for custom UI |
| Fire TV on Fire OS | Same service routes | Separate Android-based companion/client is a possible later project | Strong first TV candidate; actual model and app version matter |
| Fire TV on Vega OS | Same service routes if Plex receiver supports them | Separate Vega app/WebView integration | Separate platform; do not assume Android APK compatibility |
| Samsung Tizen TV | Same service routes | Signed separate Tizen app, with model-specific testing | Backend route preferable to modifying installed Plex |
| Android/Google TV, Roku, Apple TV | Same service routes | Separate platform adapters/apps if necessary | Investigate after first receiver passes; no blanket compatibility promise |
| Windows and hosted Plex Web | Existing companion + shared service | Existing enhanced Home/cards | Retain as the full-feature experience |

Amazon now documents [Vega and Fire OS as different development targets](https://developer.amazon.com/apps-and-games/vega),
including [Vega WebView apps](https://www.developer.amazon.com/docs/vega/0.24/develop-your-app-with-webview).
“Fire Stick support” therefore needs a specific device/OS test matrix.

Samsung provides [developer-mode testing and certificate-based deployment](https://developer.samsung.com/smarttv/develop/getting-started/using-sdk/tv-device.html)
for our own application. This does not give us an extension slot inside the
installed Plex app. Xbox similarly provides [media-app development options](https://learn.microsoft.com/en-us/windows/uwp/apps-for-xbox/development-options)
and a [separate Developer Mode workflow](https://learn.microsoft.com/en-us/windows/uwp/xbox-apps/frequently-asked-questions).
A custom player would introduce playback, subtitles, audio, HDR, remote-focus and
distribution work far beyond adding a playlist row.

## Other alternatives

- **TV-friendly Listweavarr controller:** a remote-friendly browser page or small
  launcher could expose our portrait row, then hand off to Plex. It lives outside
  Plex's Home screen; handoff must pass the same playback tests.
- **Open-source client/add-on:** an extensible client could offer deeper control.
  [Kodi](https://kodi.tv/download/) is one research candidate on supported hardware,
  but a Plex connection and our playlist behavior would still need development.
  This is an optional alternative client, not an enhancement to everyone's Plex app.
- **External HTPC connected by HDMI:** could reuse a supported enhanced client,
  at the cost of another device and remote-control UX work.
- **API/hub reverse proxy:** might alter data supplied to some clients, but client
  rendering, discovery, authentication, caching and direct connections complicate
  coverage. It cannot install arbitrary UI code in every app. Keep as an isolated
  experiment, not the primary product architecture.
- **PMS plug-in or binary/database patch:** not recommended. Plex is
  [removing legacy plug-in support](https://support.plex.tv/articles/201053748-overview/),
  and it is not a general modern client-UI extension mechanism. Do not fake
  episodes, change global watched flags, or replace server binaries to simulate
  playlist progress.

## Proposed implementation order

1. Extend the existing service with read-only receiver/session diagnostics and
   explicit session-to-playlist binding. No automatic playback or list writes.
2. Test **Resume on device** with one real TV/console, keeping the master playlist
   untouched. Verify item, timestamp and next item after the receiver starts.
3. Add checkpoint tracking for that bound session, with clear uncertainty/offline
   states. Reuse existing bookmark conflict and artwork synchronization.
4. Prototype an opt-in continuation playlist. Test native Play, timestamp behavior,
   library/Home visibility and user isolation before making it a fallback feature.
5. Expand the verified device matrix. Only consider custom TV interfaces when the
   ordinary-client routes cannot deliver an acceptable experience.

Acceptance cases: mixed movies/episodes; start in the middle; duplicate entries;
pause/stop; natural completion; next episode followed by app closure; interrupted
network/service; two users watching independently; source reorder/removal; stale
receiver discovery; direct playback of a title also present in a tracked playlist.
Never advance an unrelated list. Never report a successful resume merely because
the command was accepted. Measure the last confirmed checkpoint so potential
progress loss is visible rather than promising zero loss after power failure.

**Recommended product shape:** one optional Companion backend, initially hosted
by Listweavarr, with a clean boundary permitting a smaller standalone package
later. Share progress rules and storage across adapters. Keep the richer
Windows/Web layer, add ordinary-client TV playback first, and avoid maintaining
a modified Plex build for every device.
