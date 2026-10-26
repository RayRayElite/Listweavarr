# Approved feature roadmap

All 18 ideas were approved on October 24, 2026. Add them progressively; keep routine browsing focused on posters, titles and primary actions. Put explanations and maintenance tools behind deliberate disclosure. Audit the overall UI after several increments.

## First increment

- Official-list updates: implemented review of installed catalogue versions, preserve/exact modes, skip a version and undo the latest update. Personal removals and changes are preserved when a baseline exists. Old copies without a baseline use a conservative merge. Public hosted catalogue links and JSON file import are now supported with review-before-install.
- List health: implemented offline structural checks for exact duplicates, overlapping show/season/episode scopes, interior episode gaps, invalid scopes and unresolved identities. Findings are review notes; no automatic edits. Live verification of unavailable provider records remains future work.

## Next increments

1. Taste learning: first version implemented with More like this, Favorite and Less like this, watched history and high Plex ratings. Ownership alone supplies no positive weight. Ignored titles are not recommendation seeds. Explicit feedback is local, clearable and included in backups.
2. Explainable recommendations: implemented full reason lists in the existing Explore card menu and a collapsed title-page explanation. Reasons name seed titles and available credited people/genre/theme signals; they do not claim franchise relationships.
3. Saved discovery recipes combining mood, themes, length and availability preferences.
4. Franchise completion dashboard with essential/optional material and interest prioritisation.
5. Edition/episode-order intelligence beyond the existing continuous-to-season conversion.
6. Spoiler-safe browsing for unwatched material.
7. Tonight picker for content already available in Plex.
8. Smart acquisition priorities that help finish current watch orders.
9. Storage-aware acquisition planning by destination and quality profile.
10. Release radar for followed creators, independent of requesting everything they make.
11. Discovery inbox collecting meaningful changes with noise controls.
12. Discovery dial: familiar, adventurous or surprising recommendations.
13. Recommendation blind spots and overlooked areas of the user's taste.
14. Selectable franchise paths: essential, chronological, release and completionist.
15. Movie-night shortlist with runtime, trailers and quick elimination.
16. Recommendation feedback report with resettable influences.

## UI constraints

- Keep catalogue card actions compact; do not add a button for every feature.
- Use dedicated views for substantial workflows, contextual explanations for details, and collapsed reports for maintenance.
- Preserve fast initial rendering; expensive metadata work should be explicit or cached.
- Do not change downloads, Plex playlists or list contents merely by opening a report.


## Workbench increment ? October 24, 2026

First usable implementations now cover the remaining approved feature groups:

- Saved discovery recipes with exact theme tags, movie/TV genres, years, rating, runtime, ownership and existing language preferences. Familiar/adventurous/daily-surprise ordering operates within the returned result pool. Blind spots choose underrepresented genres.
- Tonight picker for Plex-available movies and next unwatched TV episodes with known runtime; a temporary movie-night shortlist supports elimination and random finalists. Trailers remain accessible on title pages.
- Franchise completion samples movie collections from 30 watched/recent Plex movies; it distinguishes owned, released missing and future entries. It is not a complete cross-media franchise database.
- Acquisition priorities rank saved-list gaps, partial scopes and final missing entries. Storage planning reads manager roots/profiles/free space and uses an explicit user size range; estimates do not claim exact release sizes.
- Creator release radar supports cast/crew follows, explicit checks of the next year's known projects, and independent release tracking. It does not automatically request projects.
- Discovery inbox brings together release availability, request completion, newer installed official versions and last-checked creator projects, with read state and category controls.
- Watch paths support curated essential/chronological/release/completionist selections and ordering. They can become independent local viewing lists and travel in shared/official catalogues. Default release mode uses known years rather than exact air dates; essentials/canon are never guessed.
- Edition/order tools expose TMDB episode groups, map source positions to validated aired episode IDs and append reviewed scopes. They do not equate cut/combined editions with uncut files. Existing continuous-number mapping remains available.
- Conservative spoiler mode masks descriptions, episode names, backdrops and cast until an explicit reveal; posters may still reveal information. This first version also protects watched titles rather than relying on incomplete Plex watch flags.
- Feedback insights optionally log rendered recommendation titles locally (up to 2,000) and correlate requests, Plex watches and feedback. Logging is off by default; history and taste influences can be explicitly reset without changing Plex ratings/history.

Larger workflows live in Explore > Workbench, one tool at a time. Paths/edition mapping live in List tools. Spoiler mode lives in Preferences. Reports and planning do not acquire content. Manual checks and installed-catalogue updates are functional. Hosted catalogue links and JSON-file delivery are now supported. Choosing a publisher hosting location, complete franchise canon taxonomy, and background checks while the app is closed still need future product decisions.


## Catalogue delivery follow-up

Official Lists > Updates > Get catalogue updates now supports saved public raw JSON links, catalogue file preview, reviewed installation and catalogue export. The downloader validates public addresses on every redirect and sends no service credentials. New lists and higher per-list versions merge into the catalogue; absent local entries remain, older versions are skipped, and same-version content conflicts require publisher republishing. Existing working copies are not overwritten; personal copy updates remain a separate reviewed step. The previous installed catalogue is retained in a backup. Preview tokens expire and cannot install over a concurrently edited catalogue. A default source is not preconfigured: the publisher chooses where to host exported official-lists.json.
