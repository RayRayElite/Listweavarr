# Remaining delivery work

Updated October 31, 2026. User approved proceeding with the remaining work;
TV/console cross-platform Companion implementation is explicitly deferred.
This checklist separates completed increments from full feature completion.

## Verified in this increment

- Baseline: 416 Python tests, eight browser/Companion Node harnesses, shell and
  tracked-file privacy checks passed before changes.
- Added a real release-ZIP smoke check: isolated clean startup, list creation,
  reviewed backup export/restore and restart persistence. Runs in CI too.
- Existing synthetic desktop recovery tests cover disable/reinstall, altered
  vendor index preservation and restoration. No user's Plex installation was
  uninstalled for this audit.
- Corrected stale Companion sync documentation. Live Windows tests in the user
  workflow remain distinct from automated/browser verification.
- Official feed manifest generation/checking, default public source, curator
  publication instructions and catalogue CODEOWNERS review requests.
- Composite snapshots: combine/common/subtract, exclusion, conservative exact
  identity, provenance, source-pinned preview/create and non-destructive rebuild.

- Native Plex collections now support reviewed creation and in-place updates,
  exact target identity, portrait artwork, partial-failure recovery and local
  unlinking. A disposable live add/remove/reorder test passed.
- Added title/season overview cards, cache-first Official catalogue rendering,
  linked-playlist availability checks and Upcoming release classification.
- Availability reads no longer retain the workspace lock; source/connection
  changes invalidate results, while newer request logs survive the merge.

## Remaining implementation queue

1. Extend per-list acquisition defaults with reviewed tag policies; expand request-stage diagnostics and a unified
   release calendar; additional notification transports.
2. Single-owner authentication/session recovery before an external request API.
   Household/multi-user accounts remain deferred by the user's earlier choice.
3. Unified search, optional taste onboarding, issue notebook and Plex watchlist
   bridge; manager-only discovery and optional natural-language list recipes.
4. Library readiness, duplicate/edition health, quality-profile assistance,
   protected/reviewed storage maintenance and evidence-based viewing insights.
5. Fuller composite rule lifecycle and portable curation rules. Generated
   snapshots are functional; automatic cascades and edited-result merging are not.
6. Community hosting, account ownership, publishing and moderation. No public
   Community service/account has been created. Never imply local curator mode
   proves an author's identity on a shared service.

## Live verification and external setup still required

- Complete hosted and local Plex Web playback/artwork/settings review, plus
  duplicate occurrences, final-item completion, queue edits, profile changes and
  offline sync on real clients. Automated cases exist; do not call this full
  client certification.
- Review current UI with a connected browser. A DOM harness checks behavior and
  markup, not visual layout.
- Enforce catalogue review using GitHub repository rules/settings; CODEOWNERS
  alone only requests reviewers. Verify the deployed feed after push.
- Repeat Docker checks through current GitHub CI; Docker is not installed in
  this Windows workspace. The local ZIP smoke check does not replace them.
- Select/configure Community infrastructure before deploying that service. Keep
  ordinary local installs and private lists usable without it.

No remaining feature authorizes unattended downloads, deleting media, replacing
someone's Plex target, or uploading private lists. Those workflows still require
their concrete review steps. Cross-platform research stays available in
PLEX_PLAYLIST_CROSS_PLATFORM.md for a later decision.


### Per-list acquisition defaults (2026-10-31)

Implemented local manager route, quality profile and destination overrides in
Manage list > Downloads. Both batch and TV scope reviews honor them, validate
fresh manager options and explain fallbacks. Save/reset use preference revisions;
manager configuration changes invalidate an open editor. Sharing and Official
exports exclude these local preferences. No automatic acquisition or tag policy
was added in this increment. Regression suite: 455 Python tests passed; UI harness
and frontend/release checks passed. Live visual review remains pending.
