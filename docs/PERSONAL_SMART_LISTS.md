# Personal smart-list proposals

Official Lists are shared curation. Personal smart lists should use one person's
library and viewing. Favorites and the owner's existing On Repeat collection
stay in My Lists; categorizing Official Lists does not publish personal history.

Favorites currently offers a reviewed snapshot of watched titles rated 8+/10 by
the connected Plex account or played at least twice. It is not a continuously
refreshed, profile-switching smart list. Existing On Repeat is manually curated
and must not be replaced by a generated list with the same name.

## Recommended recipes

| Priority | List | Rule and benefit |
| --- | --- | --- |
| 1 | Ready from my lists | Previously missing entries in selected lists that now have confirmed playable Plex media. An immediate watch queue. |
| 2 | Finish something | In-progress series/collections with only a few available unwatched entries left. Complete existing watches. |
| 3 | Forgotten favorites | Personally highly rated watched movies not played for a configurable period. Rediscover your library. |
| 4 | My next episodes | The next unwatched episode in each chosen active watch order. Preserve crossover chronology. |
| 5 | Short and sweet | Available unwatched movies/episodes below a chosen runtime, ranked by taste. |
| 6 | Catch up before it returns | Available unwatched episodes of followed returning shows, linked to the release calendar. |
| 7 | Comfort rotation | Personally highly rated repeat watches, optionally from chosen collections. A generated alternative to manual On Repeat. |

## Presentation and safety

Use one Create smart list action in My Lists, opening a compact recipe picker
with artwork, a short explanation and preview. No extra sidebar section.
Saved smart lists should explain their rules and offer Refresh, Pause refresh
and Convert to manual. Generated lists need unique IDs rather than replacing a
manual list by name. Refreshes must preserve deliberate exclusions.

Use the connected account's own history. Managed-profile selection and
profile-scoped rule storage are prerequisites before offering separate household
smart lists. Missing last-played dates or show rewatch counts must be disclosed;
episode totals are not rewatch counts.

Preview changes before updating lists. Linked Plex playlists still use the
existing reviewed update flow. Available-now queues must exclude missing and
upcoming titles. Never request downloads or mark titles watched automatically.


## First delivery: Ready snapshot (November 6)

The Smart lists picker now offers a reviewed Ready snapshot from saved sources.
It selects available individual movies/episodes with known unwatched/in-progress
history, optionally including unknown history, and deduplicates exact identities.
It excludes show/season scopes and uses saved comparisons rather than claiming a
new live scan. The generated list starts unchecked so its normal Plex comparison
verifies current availability. It preserves existing personal lists and has no
automatic refresh. Newly-available-only history, persistent refresh rules,
Finish something and Forgotten favorites remain follow-ups.

## Catch-up and Comfort snapshots (November 6)

The Smart lists picker now includes two more reviewed recipes:

- **Catch up before it returns:** choose saved lists containing the shows to
  follow. The preview checks actual playable, unwatched Plex episodes before a
  known future season premiere within 180 days. Regular seasons only; watched
  copies, specials, ignored titles and already-airing seasons are excluded.
  Return dates use cached TMDB calendar/title metadata. Unknown dates do not
  become guessed returns. Up to eight returning shows are checked per preview.
- **Comfort rotation:** personal Plex ratings of 8+ or repeat plays, restricted
  to chosen collections if desired. Explicit ratings below 6 are excluded.
  Show episode totals are never counted as repeat plays. Results favor strong
  personal ratings and replays, with older last-played dates breaking ties.

Both offer 25/50/100/500 entries and create a uniquely named snapshot after a
preview. They do not replace manual On Repeat, publish personal history, alter
watched flags or update Plex playlists automatically. Refresh Plex snapshot is
an explicit option. Previews expire after 15 minutes and are rejected if source
lists, ignored titles or the connected Plex account changes. Main-app recipes
still use the connected Plex account, not a selectable managed family profile.

## Home customization

Explore has **Arrange discovery rows**, with Up/Down, Save and Restore default.
Optional rows retain their saved positions when loaded later. Filtering may
hide a row without deleting its preference. This is a workspace preference,
backed up with the other settings.

Companion playlist cards now offer **Pin to front**, **Move pin left/right**
and **Unpin**. Companion Settings also lists all playlists so a playlist can be
pinned before first playback. Pins precede recent playlists, survive new
checkpoints and are isolated by Plex profile on each client. Pin order is not
currently synced between clients. Unpinning preserves resume progress;
removing from Continue Playlists also unpins it. Finished pinned playlists
remain as restartable shortcuts.

Full native Plex Home row ordering is a separate remaining step. Plex exposes
an internal HomeSettings/hubs model, but its applicability to current automatic
Home rows and keyboard/remote navigation still needs live verification. The
existing placement control changes Continue Playlists only; it is not a full
native Home reorder feature.
