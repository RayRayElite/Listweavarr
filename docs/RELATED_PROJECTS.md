# Related-project feature review

Reviewed October 26, 2026 from public READMEs and product documentation. These
are documented claims, not a runtime evaluation or a source-code audit. Similar
names refer to distinct projects. No third-party source code was copied.

## What each reference contributes

| Project | Documented capabilities worth considering | Listweavarr implication |
|---|---|---|
| [Lebbitheplow/diskovarr](https://github.com/Lebbitheplow/diskovarr) | Watch-history recommendations, exclusion controls, reviews, scoped issue reports, Plex watchlist integration and an Overseerr-compatible request API. | Extend existing taste controls; add issue tracking and compatibility after defining authentication. |
| [Diskovarr product site](https://diskovarr.com/) | Taste onboarding, combined library/provider search, Jellyfin support, playback launch and annual viewing summaries. | Consider a short optional taste setup and unified search first; defer additional media servers and detailed historical analytics. |
| [sqrlmstr5000/discovarr](https://github.com/sqrlmstr5000/discovarr) | Saved AI searches, prompt previews, scheduled generation, local-model support, usage accounting and Trakt history input. README marks the project deprecated. | Add optional natural-language discovery that resolves results to verified metadata. Keep normal discovery usable without AI. |
| [damiankw/Discovarr](https://github.com/damiankw/Discovarr) | Manager-based discovery without requiring a player connection; also supports music through Lidarr/Last.fm. | Allow a manager-only movie/TV mode, while clearly distinguishing managed titles from playable files. Music is a separate future product decision. |
| [fisherd80/Listarr](https://github.com/fisherd80/Listarr) | List-specific acquisition defaults, scheduled runs, scheduler pause, preflight checks, bulk imports and activity inspection. Also documents single-user login and encrypted API keys. | Expand L2/R2 with operational controls; investigate single-owner login independently of household accounts and plan credential migration carefully. |

The Diskovarr repository README and product site describe different release
generations. This review records concepts without claiming version parity.

## Additional proposals

| ID | Proposal | Concrete behavior and UI | Priority / dependency |
|---|---|---|---|
| O1 | Optional taste onboarding | A skippable setup with example favorites, disliked genres and discovery preferences. Results remain editable in Preferences. | Near term; extends existing taste engine |
| O2 | Unified search | One search for saved lists, library titles and provider titles, grouped by result type with owned/requested status. No external provider call per keystroke without debounce/cancellation. | Near term |
| O3 | Reliable automation controls | Per-job next run, last success, retry/backoff, bounded concurrency, global pause and connection preflight. Missed runs do not trigger uncontrolled catch-up. | Add to L2 before unattended writes |
| O4 | Playback issue notebook | Attach wrong edition, broken file, missing subtitles or audio problems to a movie/show/season/episode. Track open/resolved notes and related request history. | After R1; single-user first |
| O5 | Manager-only discovery | Work without Plex using Radarr/Sonarr metadata; show managed, downloaded and verified-in-library states distinctly. No invented watch-history personalization. | Medium |
| O6 | Native Plex watchlist bridge | Optional import and explicitly selected export, with deduplication and a preview. Explain that other installed tools may react to Plex watchlist additions. | Medium; explicit write policy |
| O7 | Natural-language list recipes | Describe a list, preview interpreted filters and verified candidates, then save an editable recipe. Optional local or remote AI; preview any library data sent remotely, show usage/cost and never auto-request generated titles. | Medium; after L4 |
| O8 | Single-owner authentication | Local owner setup, session expiry, rate limiting, recovery and migration documentation. Separate from multi-user households; keep localhost compatibility deliberate. | Before expanding remote deployment |
| O9 | Third-party request API | A documented, authenticated compatibility subset so existing dashboards can submit and inspect requests. Distinct revocable keys, scopes, duplicate protection and contract tests. | After O8 and R1 |
| O10 | Additional library adapters | Jellyfin first if demand warrants it; retain canonical identities and separate server-specific availability/history. | Later; avoid blocking Plex work |
| O11 | Personal viewing recap | A visual recap of list completion, watched titles and ratings. Only report durations/sessions when supported by actual collected data. | Extend Q5 |

## How this changes the delivery plan

1. Continue L2 with O3: source-update checks and a review queue need reliable jobs.
2. Follow with L3/L5 and R1/R2: lists should become playable, maintainable plans.
3. Add O1/O2 for easier discovery without adding more poster-card controls.
4. Implement O8 before exposing a new external API or remote household features.
5. Consider O4/O6/O7 as focused increments after those foundations.

Do not add every neighboring feature simply to match a checklist. Listweavarr's
strongest proposed distinction is the complete list workflow: mixed movie/TV/
episode curation, alternate orders, reviewed parsing, provenance, change review,
library gaps and maintained Plex publications. New integrations should improve
that workflow or remove a concrete extra service the user would otherwise need.

Before reusing any implementation, inspect that repository's actual license and
attribution requirements; a public repository alone is not permission to copy.
