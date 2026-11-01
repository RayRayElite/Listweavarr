# Architecture and contribution reference

## Read one workflow at a time

Listweavarr has a Python standard-library HTTP backend and browser-native JavaScript. There is no build step or external database. app.py starts the service; runtime_config.py supplies deployment configuration. data/state.json is private persistent state; public provider caches sit beside it. Credentials never belong in committed fixtures.

A typical change follows this path:

1. A button/event handler in web/ gathers explicit user choices.
2. api() sends JSON plus the session CSRF header to app.Handler.do_POST.
3. The route validates scope and invokes a focused backend module.
4. Slow provider reads happen outside the state lock where practical.
5. A mutation reloads state under LOCK, checks revisions and saves atomically.
6. The response renderer updates the view; previews remain distinct from confirmed external writes.

## Backend reference

The optional [Plex playlist companion](../integrations/plex-playlist-companion/README.md)
is separate from the HTTP application. `bookmarks.js` holds offline identity and
resume rules; `plex-adapter.js` owns version-specific player/transport integration;
`home.js` owns the portrait resume row and local artwork; `runtime.js` initializes
them. `desktop.py` installs/restores only verified client assets. Its Python and
Node tests are included in CI. Do not add Plex credentials or proprietary client
bundles to fixtures.

| Module | Responsibility | Useful entry points |
|---|---|---|
| [app.py](../app.py) | HTTP application and workflow orchestration. | `start_import_job`, `refresh_request_state`, `dispatch_discord_once`, `start_background_tasks`, `public_state`, `plex_account` |
| [providers.py](../providers.py) | List import adapters and primary TMDB metadata. | `import_options`, `arrange_import`, `validate_url`, `ProviderRedirects`, `fetch`, `Node` |
| [companion.py](../companion.py) | Discovery workbench: Favorites, Tonight, planning and notifications. | `today`, `validate_state`, `recipe`, `discover`, `tonight`, `franchise` |
| [explore.py](../explore.py) | Library-aware discovery shelves and public list browsing. | `library`, `title_key`, `normalized_title`, `ownership`, `card`, `qualifies` |
| [saved_lists.py](../saved_lists.py) | Validated edits to personal collections. | `revision`, `poster`, `edit`, `identity_keys`, `update_entries` |
| [composite_lists.py](../composite_lists.py) | Read-only exact-identity set operations and source-pinned generation. | `recipe`, `exact`, `Index`, `preview`; see COMPOSITE_LISTS.md |
| [list_sharing.py](../list_sharing.py) | Portable list interchange without private runtime state. | `digest`, `export`, `validate` |
| [list_updates.py](../list_updates.py) | Read-only linked-source differences and opt-in scheduling. | `fingerprint`, `summarize`, `due`, `finish`, `public`; orchestration in `app.check_linked_list` |
| [plex_publications.py](../plex_publications.py) | Saved Plex target snapshots and publication differences. | `baseline`, `target`, `changes`; reviewed writes use `app.create_playlist` |
| [plex_collections.py](../plex_collections.py) | Native collection plans, exact target identity, paged membership and guarded in-place updates. | `kind`, `libraries`, `plan`, `target`, `apply`; tokens/checkpoints in `app.collection_action` |
| [list_release_state.py](../list_release_state.py) | Cache-first detection of unreleased list scopes with bounded current/future-year metadata refresh. | `upcoming` |
| [official_lists.py](../official_lists.py) | Versioned Official catalogue authoring and personal-copy creation. | `prepare_publish`, `write_document`, `document`, `catalogue`, `get`, `instantiate` |
| [collection_tools.py](../collection_tools.py) | Collection diagnostics and reviewable version merges. | `portable`, `snapshot`, `key`, `indexed`, `health`, `preview` |
| [catalogue_feed.py](../catalogue_feed.py) | Public catalogue download, manifest checks and staged installation. | `digest`, `source_url`, `download`, `validate`, `compare_content`, `merge` |
| [text_list_builder.py](../text_list_builder.py) | Text, article and spreadsheet interpretation into proposed list entries. | `public_target`, `google_sheet_export`, `extract_sheet`, `sheet_tabs`, `fetch_workbook`, `fetch_page` |
| [parallel_orders.py](../parallel_orders.py) | Explicit parallel blocks and round-robin verified episode expansion. | `prepare`, `annotate`, `expand`; see [parallel watch orders](PARALLEL_WATCH_ORDERS.md) |
| [request_ledger.py](../request_ledger.py) | Durable records of reviewed acquisition and monitoring requests. | `fingerprint`, `routed_fingerprint`, `record`, `migrate`, `apply_status`, `public` |
| [manager_routes.py](../manager_routes.py) | Named Radarr/Sonarr instances and route-specific defaults. | `validate_url`, `choices`, `public`, `config`, `routed`, `default` |
| [activity.py](../activity.py) | Read-only download queue and manager status summaries. | `cached`, `queue`, `queue_label`, `summarize` |
| [release_watch.py](../release_watch.py) | Regional movie release dates and TV premiere tracking. | `region`, `availability`, `tv_availability`, `check`, `tracked_item`, `monitor` |
| [ratings.py](../ratings.py) | Provider-labelled ratings and user display preferences. | `preferences`, `number`, `NoRedirect`, `request`, `parse`, `lookup` |
| [metadata_sources.py](../metadata_sources.py) | Optional Wikidata, AniList and TheTVDB metadata. | `NoRedirect`, `request_json`, `cached`, `safe_link`, `claims`, `entity_ids` |
| [title_relationships.py](../title_relationships.py) | Confirmed movie/TV relationship classification and ordering. | `sections` |
| [suggestions.py](../suggestions.py) | Broader title-to-title discovery signals. | `discover` |
| [trakt_features.py](../trakt_features.py) | Public Trakt lists, ratings, recommendations and calendars. | `cached_get`, `list_card`, `search_lists`, `resolve_title`, `title_lists`, `title_features` |
| [ignored_titles.py](../ignored_titles.py) | Persistent identity-based exclusions. | `tokens`, `matches`, `add` |
| [poster_overlays.py](../poster_overlays.py) | Browser-only TV poster status and optional network artwork. | `asset_path`, `show_info` |
| [backups.py](../backups.py) | Credential-scrubbed portable workspace backups. | `sensitive`, `scrub`, `export`, `digest`, `validate`, `restore` |
| [discord_notify.py](../discord_notify.py) | Optional outbound request/release notifications. | `validate_url`, `public`, `configure`, `collect`, `NoRedirect`, `DeliveryError` |
| [indexer_discovery.py](../indexer_discovery.py) | Optional read-only Prowlarr popularity observations. | `identity`, `normalized`, `release_title`, `resolve_search`, `candidates` |
| [popular_downloads.py](../popular_downloads.py) | Public movie/TV download-popularity discovery adapters. | `ChartParser`, `fetch`, `source_rows`, `candidates` |
| [cult_discovery.py](../cult_discovery.py) | Curated enjoyable-bad eligibility with taste/history ranking. | `curated_candidates`; legacy `score`/`candidates` remain for comparison, not Explore fallback |
| [taste.py](../taste.py) | Personal preference signals for discovery. | `validate`, `identity`, `record`, `catalog_with_feedback`, `affinity`, `rank` |

runtime_config.py owns data paths, host allowlists, public URL and local curator mode. These are shared by the entry point, provider caches and Docker.

## Browser reference

| File | Start here for |
|---|---|
| web/index.html | Persistent shell IDs, dialogs and script load order |
| web/app.js | Shared state, entry rendering, API helper, metadata loading, title and request dialogs |
| web/lists.js | Personal catalogue, editor, sharing, list covers and local Official publication |
| web/list-updates.js | Source-update summaries, manual checks and opt-in daily/weekly scheduling |
| web/collections.js | Explicit library choice, collection diff review and single-use publication |
| web/official-cache.js | Persistent catalogue-card snapshots, excluding library inventory/credentials |
| web/explore.js | Discovery shelves, filters, list searches and selection routing |
| web/trakt.js | List previews, followed calendar and title-related discovery |
| web/workbench.js | Workbench actions, creator follows, planning and watch-path editing |
| web/discovery-updates.js | Favorites builder, grouped list management, native links, session plans and notification presentation |
| web/collection-tools.js | Catalogue manifests, staged updates, personal-copy merges and health checks |
| web/requests.js / workflow.js | Request history, review/retry, manager routing and explicit decisions |
| web/workspace.js / audit-workflows.js | Layout composition, tabs, accessible task choices and preference sections |
| web/navigation.js | Addressable routes, browser back/forward and warm-start restoration |
| web/enrichment.js / taste.js | Extra metadata, relationships and preference feedback |
| web/style.css / workspace.css | Base theme followed by composed workflow layouts |

Scripts intentionally share globals today. Initialization order matters. Preserve the Node harness when replacing an event handler; it executes the real scripts. New features should use existing API/render boundaries instead of adding another layer of wrappers without documenting the order.

## Find a feature

- Text list import: web/builder.js ? /api/lists/build/* ? text_list_builder.py ? saved_lists.py.
- Favorites: web/discovery-updates.js ? /api/companion/favorites ? Plex catalogue + companion.favorites ? reviewed /api/lists/edit.
- Discovery: web/explore.js ? /api/explore/* ? explore.py + taste.py + provider metadata.
- Acquisition: list/title/request review ? /api/request, show/request or requests/retry ? validated manager route ? request_item ? request_ledger.
- Plex playlist: playlist preview ? user confirmation ? create_playlist; verify order before deleting a replaced playlist.
- Official updates: manifest check ? explicit catalogue download/install ? separate personal-copy review ? separate Plex playlist update.
- Release tracking: release_watch.py tracks dates; explicit monitoring confirmation chooses a manager route. A tracking checkbox alone is not an acquisition request.

## Tests and maintenance commands

Tests are grouped by feature under tests/. External services use mocks and synthetic records. The fixture README records the origin of factual title/numbering samples. test_ui.cjs checks client event handlers without a browser; browser review is still required for meaningful layout changes.

scripts/ contains optional live diagnostics, the explicit publisher CLI, release checks and archive building. A live diagnostic may read your configured services and write private aggregate reports under data/; it is not required to run the app or contribute a pure unit test.

## Important invariants

The optional Plex companion lives in integrations/plex-playlist-companion/.
bookmarks.js owns offline checkpoints and opt-in cross-device exchange;
playlist_progress.py validates and merges shared bookmarks. app.py enforces the
separate progress capability and origin/host boundary. Artwork credentials cannot
write progress. Clients resolve offline conflicts by playback timestamp and
re-check the active profile after network waits. tests/test_playlist_sync.cjs and
tests/test_playlist_progress.py cover these contracts.

- Similar text is not proof of matching identity, ownership or franchise membership.
- Movie, show, season and episode scopes stay distinct throughout imports and requests.
- An existing manager file is not proof that Plex has imported it.
- Previewing, searching, checking updates or sorting never authorizes acquisition/publication.
- Portable files exclude credentials, Plex keys and request history.
- Catalogue updates and code updates are separate; incompatible schemas may still require an app upgrade.
- Local curator mode is not authentication. Shared publication authority belongs to repository/server permissions.
- The app is trusted single-user software, not an Internet-facing multi-user service.


## Per-list acquisition defaults

`app.request_options` merges validated local list defaults over service/route
remembered defaults. `/api/lists/acquisition/{options,save,reset}` reads managers
outside the state lock and checks preference revisions and manager signatures
before saving. `web/discovery-updates.js` owns the dedicated Manage list editor;
`requestRouteMarkup` and `web/workflow.js` carry the original list context when
switching routes. `tests/test_list_acquisition.py` covers isolated defaults,
invalid options, changed routes, revision conflicts, offline reset and export
privacy. Saving preferences must never call manager write APIs.


## Request diagnostics and release calendar

`activity.diagnostic` turns exact-scope queue evidence into bounded, redacted
explanations and suggested checks. It does not perform extra manager calls or
writes. `request_ledger.apply_status` retains last confirmed states on read
failures and maps manager files to the imported stage. `web/requests.js` keeps
raw evidence behind disclosure controls. Tests live in
`tests/test_request_diagnostics.py`.

`release_calendar.py` assembles a read-only month snapshot from tracked releases,
followed lists and creator credits. Cached reads make no network calls; refresh
has a 50-record TMDB budget and optional Trakt month queries. Exact identity,
date, format and region determine deduplication. A bounded in-memory Trakt
snapshot survives navigation but is invalidated by follow/account changes.
`/api/calendar` reads a state snapshot outside slow provider work and does not
write user state. `web/calendar.js` owns the Explore tab, source filters, agenda,
month grid, cached-first behavior and stale-response guards. Calendar JS loads
before navigation so shareable `#/explore/calendar` routes work. Python tests
cover date boundaries, provenance, region, scope and failure handling;
`tests/test_calendar_ui.cjs` exercises the actual renderer and async races.


## Acquisition tags, notification transports and session renewal

`acquisition_tags.py` validates existing manager tag IDs and merges selections
without removing existing tags. The routed `_request_tags` snapshot is populated
only from reviewed options; both immediate requests and release monitoring validate
live tags before writes. `request_ledger` retains selected IDs for approvals/retries.
`requestTagsMarkup` carries selections through batch, TV scope and retry reviews.

`notification_channels.py` provides ntfy, Gotify and generic webhook transports,
quiet-hour and digest selection. It reuses `discord_notify`'s bounded event cursor,
outbox and retry engine through isolated per-service views. `dispatch_channel_once`
collects under the state lock, sends outside it and validates destination identity
before recording completion. Tokens are not exposed by its public response or
portable backups. `web/notifications.js` owns the optional settings panel.

`/api/session` renews the local CSRF token. POST rejects stale tokens with a distinct
`session_expired` code before body parsing/action dispatch; `api()` retries once
only for that explicit rejection and coalesces concurrent renewals. Tests include
`test_acquisition_tags.py`, `test_notification_channels.py`, and both Python/Node
`test_session_recovery` harnesses.


## Optional owner access

`owner_access.OwnerAccess` is initialized once from an optional operator password
file. It uses a scrypt verifier, a private random key, hashed opaque sessions,
seven-day expiry and persistent revocation. `Handler` gates state/job/normal API
routes, exposes same-origin JSON sign-in and CSRF-protected sign-out, and serves
`web/sign-in.html` before the main shell. Paired Companion endpoints keep their
existing scoped bearer-token guards. `web/access.js` reports the mode in Settings.
`tests/test_owner_access.py` covers persistence, rotation, logout, expiry, rate
limits, HTTP gating and Companion authorization boundaries. See OWNER_ACCESS.md
for deployment and recovery; authentication remains off in existing local installs.


## Search, issue notes and list membership

- `unified_search.py` ranks local read-only snapshots separately from paged TMDB search. Exact scoped provider identities reconcile matches; `explore.peek_library` never waits for a network scan.
- `web/search.js` controls cancellation, separate local/provider results and pagination. `api` accepts an optional abort signal while retaining the explicit session-expiry retry rule.
- `issue_notebook.py` validates private notes, immutable title identity, edit revisions and exact related request scope. `web/issues.js` owns notebook/editor state and unsaved-draft protection. Backup validation includes notes; public exports exclude them.
- `saved_lists.remove_entries` reuses ordinary edit revision, source-detachment and publication-dirty rules. `append_lists` snapshots ordered sources, gives entries new IDs and strips availability/request data. Routes pin target and source revisions under the state lock; lightweight append-options avoids downloading all list posters.
- Person project `credit_types` distinguishes acting from directing independently of character-name text. Project publication saves selected keys in reviewed order, compares availability, then reuses `openPlaylistPreview`.
- Companion `bookmarks.dismiss` writes a profile-scoped timestamped dismissal instead of deleting data. Existing newest-checkpoint sync transports it; fresh playback restores visibility. `home.js` renders the native-style card options.
