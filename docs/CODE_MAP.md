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

| Module | Responsibility | Useful entry points |
|---|---|---|
| [app.py](../app.py) | HTTP application and workflow orchestration. | `start_import_job`, `refresh_request_state`, `dispatch_discord_once`, `start_background_tasks`, `public_state`, `plex_account` |
| [providers.py](../providers.py) | List import adapters and primary TMDB metadata. | `import_options`, `arrange_import`, `validate_url`, `ProviderRedirects`, `fetch`, `Node` |
| [companion.py](../companion.py) | Discovery workbench: Favorites, Tonight, planning and notifications. | `today`, `validate_state`, `recipe`, `discover`, `tonight`, `franchise` |
| [explore.py](../explore.py) | Library-aware discovery shelves and public list browsing. | `library`, `title_key`, `normalized_title`, `ownership`, `card`, `qualifies` |
| [saved_lists.py](../saved_lists.py) | Validated edits to personal collections. | `revision`, `poster`, `edit`, `identity_keys`, `update_entries` |
| [list_sharing.py](../list_sharing.py) | Portable list interchange without private runtime state. | `digest`, `export`, `validate` |
| [official_lists.py](../official_lists.py) | Versioned Official catalogue authoring and personal-copy creation. | `prepare_publish`, `write_document`, `document`, `catalogue`, `get`, `instantiate` |
| [collection_tools.py](../collection_tools.py) | Collection diagnostics and reviewable version merges. | `portable`, `snapshot`, `key`, `indexed`, `health`, `preview` |
| [catalogue_feed.py](../catalogue_feed.py) | Public catalogue download, manifest checks and staged installation. | `digest`, `source_url`, `download`, `validate`, `compare_content`, `merge` |
| [text_list_builder.py](../text_list_builder.py) | Text, article and spreadsheet interpretation into proposed list entries. | `public_target`, `google_sheet_export`, `extract_sheet`, `sheet_tabs`, `fetch_workbook`, `fetch_page` |
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
| [cult_discovery.py](../cult_discovery.py) | Heuristic so-bad-its-good discovery. | `score`, `candidates`, `review_evidence`, `canonical` |
| [taste.py](../taste.py) | Personal preference signals for discovery. | `validate`, `identity`, `record`, `catalog_with_feedback`, `affinity`, `rank` |

runtime_config.py owns data paths, host allowlists, public URL and local curator mode. These are shared by the entry point, provider caches and Docker.

## Browser reference

| File | Start here for |
|---|---|
| web/index.html | Persistent shell IDs, dialogs and script load order |
| web/app.js | Shared state, entry rendering, API helper, metadata loading, title and request dialogs |
| web/lists.js | Personal catalogue, editor, sharing, list covers and local Official publication |
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

- Similar text is not proof of matching identity, ownership or franchise membership.
- Movie, show, season and episode scopes stay distinct throughout imports and requests.
- An existing manager file is not proof that Plex has imported it.
- Previewing, searching, checking updates or sorting never authorizes acquisition/publication.
- Portable files exclude credentials, Plex keys and request history.
- Catalogue updates and code updates are separate; incompatible schemas may still require an app upgrade.
- Local curator mode is not authentication. Shared publication authority belongs to repository/server permissions.
- The app is trusted single-user software, not an Internet-facing multi-user service.
