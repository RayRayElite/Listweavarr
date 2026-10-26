# Changelog

## Unreleased

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
