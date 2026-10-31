# Changelog

## Unreleased

- Select multiple My Lists or Official Lists and preview/create a Plex playlist
  for each, with editable names, availability counts, saved artwork and individual
  results. Existing playlists stay intact; failed rows do not stop the batch.

- Preserve poster upload bytes through the Plex Direct HTTPS DNS fallback so
  newly created playlists receive their selected Listweavarr artwork.

- Expand bundled Official Lists to 57 curated collections and 14,069 entries.
  Favorites and So Bad Its Good remain personal; bundled lists exclude artwork.

- Sync companion pencil-selected posters between paired clients, including legacy
  desktop artwork, with profile-scoped private storage and local-choice protection.

- Support artwork pairing and bookmark sync in Plex desktop's older Chromium
  runtime without AbortSignal.timeout; clear request timers on completion.

- Add optional cross-device playlist bookmark sync through Listweavarr, with
  migration of local checkpoints, offline fallback, timestamp conflict handling,
  separate revocable progress credentials and per-user/server/playlist keys.
- Package a clean Chrome extension folder and reversible Windows companion
  updater, native portrait layout metrics and optional cached Listweavarr artwork.

- Accept Plex's partial queue windows for middle-entry playlist starts when the
  server confirms the playlist ID and absolute selection, and every returned
  entry matches its anchored position. Verified against the real 200-item
  MindFuck Collection response, which returns 199 entries at position 165.

- Verify native playlist starts even when the observed request never invokes its
  response callback. Require a recent explicit playlist request and an exact
  full ordered match between the new active queue and the playlist before saving.

- Retain native playlist response identity across intervening queue requests.
  Match that identity to the actual active queue/user/server instead of dropping
  it solely because another request was observed before its response arrived.

- Carry explicit native playlist request identity to the matching active player
  queue when connection aliases differ and Plex omits a playlist source URI.
  Keep user, server, queue and playback-intent checks before binding.

- Recognize native playlist playback through verified active-queue source metadata
  as well as queue creation requests, including starts in the middle of a list.
  Accept explicit playlist parameters in request data and encoded source URIs.
  Desktop verification with additional playlists is pending.

- Refresh Continue Playlists after silent desktop Stop transitions, retaining the
  newest saved time rather than an older model snapshot. Keep refresh requests
  raised during an in-flight home-row load.

- Persist bound playlist progress on player changes and before Stop clears the
  player, with window-close and periodic fallbacks. Record the final reported
  second as completion, resume at the next item, and remove finished playlists
  from Continue Playlists. Desktop Stop/completion live verification is pending.

- Observe explicit playlist queue creation from normal Plex desktop Play controls
  for automatic bookmark binding. Add a portrait Continue Playlists home row,
  one-click resume and optional device-local artwork. The user confirmed the row
  and resume work. Place it after the complete Continue Watching hub and expose
  poster editing through a hover/focus pencil. Final placement verification is
  pending; native playlist-grid poster dimensions are unchanged.

- Add a version-specific desktop playlist player adapter and development controls
  for Start, Resume and Pause & save. It reads full playlist contents, validates
  the queue's selected occurrence, and observes progress only in the explicitly
  bound queue/profile. A live 641-entry playlist test verified desktop episode
  resume after restarting Plex and preserved playlist Up Next. This remains an
  experimental source-checkout integration with limited client compatibility.

- Start an optional standalone Plex playlist companion prototype: shared offline
  bookmark rules, a reversible version-checked Windows loader, and a minimal
  browser-extension bootstrap. Desktop script loading and storage availability
  have been verified; automatic tracking, poster layout and queue resume are
  not implemented yet. See `integrations/plex-playlist-companion/README.md`.

- Import structured show/episode-name spreadsheets even when they contain only
  custom release codes rather than season/episode numbers. Match titles across
  the parent's catalogue, retain ambiguities, and normalize conjunctions and
  multipart labels without fuzzy matching spelling discrepancies.

- Separate parenthesized years and media labels (movies, short films, TV/web
  series, anime, OVAs and specials) from search titles. Keep movie sequence labels
  out of queries, distinguish catalogue totals from requested scopes, and retain
  explicitly selected episodes on multi-episode lines. Missing titles require
  correction. Specials remain reviewable rather than being assumed to be films.

- Automatically detect named continuous episode ranges without a season. Map
  across verified TMDB season records, including anime that retain continuous
  episode identifiers within seasons. Preserve interspersed movies and expose
  expanded-order preview for these ranges. See
  [continuous numbering](docs/CONTINUOUS_EPISODE_NUMBERING.md).

- Parse explicit parallel notes and scoped slash-separated shows into alternating
  episode blocks, first listed title first. Review lane labels and expanded order,
  or make a block sequential. Unequal lanes finish without dropping episodes;
  ambiguous references and incomplete scopes require correction.

- Handle JavaScript-escaped Google Sheets tab names, skip episode-sheet language
  subheaders and expand NCIS: LA/NO aliases. Added a reusable order-preserving
  source alignment helper that reports contradictory anchors for review.

- So-bad-it's-good recommendations now take eligibility from the saved list
  named So Bad Its Good. Personal taste, watched/highly rated titles, credited
  people, genres and themes rank the curated candidates; no heuristic filler is
  added. Pools rotate daily and load in bounded pages. Existing ownership,
  ignore, tracking and language filters remain; rating minimums are bypassed.

- Merge supported Trakt, Letterboxd, IMDb, MDBList and ChronoCanon links into a
  list draft, with preview, exact-scope deduplication and linked-list detachment
  confirmation. Preserve parent-show IDs when saving TV entries in the editor.
- Review and update saved Plex playlist targets with expiring previews,
  availability/remote drift checks and verification before replacing old targets.

- Apply the exact reviewed linked-source snapshot and undo its last application.
  Review the complete proposed order in increments, with previous-position
  markers. Stale previews and undo after intervening content edits are rejected.

- Linked source-update panel with opt-in daily/weekly read-only checks, pause,
  retry backoff, change summaries and stale-result protection. Incomplete or
  uncertain provider responses do not imply removals. No automatic list edits,
  Plex changes or acquisition requests.
- Fixed CSV export routing and added end-to-end HTTP coverage.

## 0.5.0 - 2026-10-26

- Rename the application to Listweavarr; retain legacy shared files and local browser preferences.
- Add non-root persistent Docker deployment with configurable host validation.
- Separate redistributable catalogue data from private runtime files and artwork.
- Add contributor guides, code references, automated tests and container smoke checks.
- Establish AGPLv3 source licensing and Git version history.

# Listweavarr 0.4.0 release candidate

Verified 2026-10-23 (America/Toronto).

- Optional live MDBList ratings validated: ten sources for the sampled movie, five for the sampled TV series. Native scales retained; episode/season scores do not inherit series scores.
- Credential-free portable backups, validated merge/replace previews, a safety snapshot before restore, and ten rolling workspace backups.
- Read-only manager progress and scoped duplicate-search guards. Plex availability remains a separate comparison result.
- Throttled sorting redraws and metadata failure/retry controls.
- Cached summary audit: Halloween 702 entries (two incorrect source movie IDs); MCU mixed timeline 655 entries (zero summary/artwork failures). Warm passes completed in approximately 0.2 and 0.5 seconds respectively; these are cached backend timings, not cold network benchmarks.
- Live provider and mixed-list checks preserve source order. Downloads and actual Plex playlist creation were not performed during verification; write paths are covered by isolated tests.

## Items requiring source review

The Halloween list imports Salem's Lot (IMDb tt0079844) and Over the Garden Wall (tt3718778) as movies, but their exact IMDb cross-references resolve to TV titles. Use Correct match to select the TV-show identity and compare again. Automatic scope conversion is intentionally not performed.

The external ChronoCanon Pok?mon sample retains 47 entries but reports 48 matching/scope warnings. Its unresolved items need review before acquisition. Third-party episode and season ordering can require explicit provider identifiers; an unresolved segment never authorizes a whole-show download.

Ratings, release dates and discovery coverage depend on upstream providers and account quotas. Release notices are in-app and only check while Listweavarr is opened/running. The app remains a local personal tool, not an unattended download service.
