# Listweavarr expansion roadmap

Planning baseline: October 26, 2026. These are proposed increments, not claims
that every integration or automation already exists. Existing features are
documented in ROADMAP.md; this plan extends them rather than duplicating them.

Additional discovery/list-manager references and eleven follow-up proposals are
tracked in [Related-project review](RELATED_PROJECTS.md). In particular, O3
extends L2 with reliable scheduler controls; O8 separates single-owner login from
the deferred multi-user household milestone.

## Product direction

Lists are the organizing unit: discover, curate, complete, watch and maintain a
library through lists. Reduce separate dashboards and optional services where
practical. Keep Radarr/Sonarr and download clients as acquisition engines for
now; replacing those engines would introduce a substantially larger maintenance
and compatibility burden. Adopt useful workflows, not another project's code
or identity. Check licensing before reusing implementations.

## Prioritized feature backlog

| ID | Feature | Existing foundation and next deliverable | Placement |
|---|---|---|---|
| L1 | Spreadsheet portability | JSON sharing exists. Add ordered CSV export with public IDs, movie/show/season/episode scopes and spreadsheet formula escaping. | Existing Share dialog |
| L2 | List update control center | Source refresh and reviewed Official updates exist. Add scheduled checks, additions/removals/reorders preview, last-success timestamps, failures and per-list policies. | Lists / Updates |
| L3 | Managed Plex publications | Playlist creation exists. Save publication targets and review a diff before updating playlists or movie/TV collections. Mixed-media lists remain playlists. | List / Publish |
| L4 | Smart and composite lists | Recipes and watch paths exist. Add saved union/intersection/difference rules, exclusions, deduplication and provenance. Keep generated results separate from manual edits. | List editor / Rules |
| L5 | Resume this watch order | Watched progress exists. Show next playable item, missing blockers and alternate paths without losing curated sequence. | List header |
| L6 | Curator release workflow | Local Official authoring exists. Add validated releases, changelogs, publisher identity verification and configurable update channels. Users choose installation and Plex updates separately. | Official / Updates |
| L7 | Community catalogue | File sharing exists. Add opt-in publishing, search, attribution, reports and moderation after choosing a hosted service. Private lists stay private. | Lists / Community |
| R1 | Request troubleshooting | Durable request history and queue reads exist. Explain waiting, download, import failure and library-scan stages with actionable diagnostics. Never equate manager presence with playable availability. | Requests / Needs attention |
| R2 | Scoped acquisition policies | Review and manager routes exist. Add per-list destination/profile/tag policies, preview affected titles and prevent repeat submissions across lists. | List / Acquisition |
| R3 | Unified release calendar | Release tracking exists. Add month/agenda views combining followed lists, creators and release watchlist; distinguish theatrical and home release dates. | Explore / Calendar |
| R4 | Notification delivery options | Discord and inbox exist. Add ntfy, Gotify and generic webhooks with event selection, batching, quiet hours and delivery history. | Settings / Notifications |
| R5 | Household requests | Deferred while single-user remains the chosen mode. Add authentication, roles, approval rules, quotas and per-user privacy before enabling remote household access. | Separate later milestone |
| Q1 | Quality profile assistance | Manager roots/profiles exist. Compare desired profiles and custom formats, preview changes and preserve user overrides. Begin read-only; do not silently replace manager settings. | Settings / Quality |
| Q2 | Watch readiness | Show missing audio/subtitle languages, resolution and playable-file status. Begin with Plex stream metadata; optionally connect Bazarr before considering a native subtitle downloader. | Title / Readiness |
| Q3 | Library health | Add duplicate editions, unmatched titles, broken references and inconsistent episode orders. Report evidence and remediation choices. | Library / Health |
| Q4 | Storage maintenance | Storage planning exists. Add reviewable watched/stale candidates, keep-forever protection and list-dependency warnings. Deletion requires explicit review; no automatic cleanup by default. | Library / Storage |
| Q5 | Useful viewing insights | Plex watches/ratings inform recommendations. Add completion trends, abandoned orders and underused collections. Detailed historical session analytics require additional collection or an optional Tautulli connection. | Library / Insights |
| D1 | List-aware discovery | Explain which collections a suggestion completes, identify missing bridges and avoid recommending tracked/acquired titles repeatedly. | Existing discovery cards |
| D2 | Portable personal curation | Export/import rules, alternate paths and preferences with a clear public/private field preview. Shared files must never include service credentials. | Existing sharing workflow |

## Delivery order and acceptance gates

1. **List foundations:** L1, L2, L3, L5. This is the clearest product difference.
2. **Acquisition confidence:** R1, R2, R3, R4. Reduce reasons to open other dashboards.
3. **Power curation:** L4, L6, D1, D2. Build on reliable identities and update diffs.
4. **Library care:** Q2, Q3, Q1, Q4, Q5. Start read-only and add reviewed writes.
5. **Shared ecosystem:** L7, then R5 only when household support is requested.

Each increment must have an explicit empty/loading/error state, bounded provider
requests, cached initial rendering, meaningful regression checks and contributor
documentation. No extra action buttons on every poster. Reuse contextual menus;
substantial tasks get dedicated views. Feature discovery should not require
reading a wall of settings.

## Reference projects and scope

- [Seerr](https://docs.seerr.dev/using-seerr/settings/general/): request and discovery workflows; [notification agents](https://docs.seerr.dev/using-seerr/notifications/) inform R4.
- [Kometa](https://kometa.wiki/en/latest/files/overview/): collection, playlist and overlay configuration informs managed publications. Full overlay parity is not required for L3.
- [Maintainerr](https://docs.maintainerr.info/rules/): rule-based maintenance informs Q4, with review and protected-list safeguards here.
- [Recyclarr](https://next.recyclarr.dev/guide/features/): configuration synchronization informs Q1. Begin with a comparison rather than replacing existing profiles.
- [Bazarr](https://www.bazarr.media/): subtitle management informs Q2; detection and integration precede implementing an entire subtitle provider ecosystem.
- [Tautulli](https://docs.tautulli.com/): viewing analytics informs Q5; do not imply Plex supplies complete historical sessions retroactively.

These references describe inspiration and integration opportunities, not promised
full replacements. Native workflows can remove optional companion services over
time, while specialized download engines remain supported.

## Work started

- L1: CSV export added to the existing Share dialog. Preserves list order and
  public identifiers, handles quoted/multiline titles, and excludes private
  runtime fields. Shared JSON remains the full-fidelity format for list covers,
  descriptions and alternate watch paths.
- L2/O3 first increment: opt-in daily/weekly linked-source checks, a global pause,
  single-check concurrency, durable next-run/last-success state, retry backoff and
  added/removed/reordered summaries in Lists / My Lists / Source updates.
  Supported sources: Trakt, Letterboxd, MDBList, IMDb and ChronoCanon. Checks
  reuse the supported import adapters and reject warnings rather than treating
  uncertain results as authoritative. Article/spreadsheet/file imports remain
  manual. Schedules run only while the application is running; missed intervals
  produce one check, not a backlog. Review details are capped at 200 added and
  200 removed titles. No list membership, Plex publication or downloads change.
- Next L2 increment: staged application/undo of a checked source version, full
  order comparison and a dedicated update queue. Current summaries guide an
  explicit source refresh; they do not pin that later refresh to the checked
  provider version. L3 managed publications follows that foundation.
