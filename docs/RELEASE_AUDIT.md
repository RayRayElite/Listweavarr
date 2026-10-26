# Listweavarr 0.5.0 release-preparation audit

Date: 2026-10-26

## Version control

The public repository is https://github.com/RayRayElite/Listweavarr. A source checkpoint precedes the branding/deployment work, followed by focused release-preparation commits. Git tracks application source, tests, documentation, original SVG assets and a scrubbed public catalogue. It never tracks local data or credentials. Release tags identify known-good code; data backups are a separate responsibility.

## Cleanup and organization

- Removed 64 verified-empty temporary test directories. No directory containing files was deleted.
- Moved diagnostic, publishing and archive commands into scripts/.
- Moved the illustrative CSV into examples/lists/.
- Moved the feature roadmap and comprehensive guide into docs/.
- Put factual parser regression samples under tests/fixtures/; omitted full website captures and unused provider dumps.
- Retained focused backend modules at the root deliberately to avoid a risky package/import migration in the first public release.
- Preserved local private artwork under data/private-assets/kometa and the working catalogue under data/catalogue. These are ignored, not redistributed or deleted.
- Kept caches, audit screenshots, developer tools, backups and generated release files private/ignored.

## Branding and compatibility

UI, startup commands, docs, client callbacks, headers and service identification use Listweavarr. Legacy v1 shared-file identifiers, local browser storage keys, the previous CSRF header and curator environment variable remain compatible. The browser was checked with the existing user workspace after restart.

## Documentation and contribution readiness

Expanded compressed Python and browser code with pinned formatters, added module contracts and labelled core workflow sections, and documented feature ownership/API paths in CODE_MAP.md. CONTRIBUTING.md explains tracing a workflow, tests, mocks, data privacy and review boundaries. README, deployment/security guides and AGPLv3 licensing cover local and container use.

## Distribution hygiene

The public catalogue contains title IDs/order, descriptions and paths but no embedded posters, Plex keys, connection settings or request/watch history. Private ThePosterDB artwork and unverified Kometa/network logo assets are excluded from Git, runtime ZIPs and the Docker build context. Original SVG status ribbons provide a redistributable fallback. THIRD_PARTY_NOTICES.md explains provider/data rights and required attribution.

A tracked-file privacy gate checks excluded paths, likely credentials and catalogue contents. A separate explicit archive allowlist prevents local files from leaking through a broad recursive copy. This is defense in depth, not a guarantee that every possible secret format can be recognized automatically.

## Verification

338 Python tests passed locally, with the client regression harness, static frontend validator, archive integrity and tracked-file privacy checks. GitHub CI passed on Python 3.11 and 3.14 in a clean Linux checkout. The real Docker image built and ran as non-root with a read-only application filesystem, checked health/UI/Host protection and persisted synthetic data across restart. CI additionally checks volume persistence after container recreation. Docker is not installed on the developer Windows machine; container validation is performed in GitHub CI.

The app remains single-user trusted-local/LAN software with no login. Default container publishing is localhost-only; remote access requires an authenticated proxy/private network. Public Community hosting, a curated publisher service and registry-hosted images are not claimed as deployed. Docker Compose builds this release from source.
