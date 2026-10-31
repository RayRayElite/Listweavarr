# Listweavarr

A personal, local browser app for importing ordered movie / TV lists, comparing them with Plex, creating playlists, and submitting reviewed requests to Radarr and Sonarr.

## Explore your library's next additions

**Explore** is the discovery workspace. It uses your connected Plex account's movie/show catalogue, watched flags, genres, user ratings where available, and recent viewing/addition times. Watched titles carry more weight than collected titles; low personal ratings reduce their influence. A bounded sample of library titles supplies cast, filmmaker, keyword and collection signals. This is a transparent content-based approximation of your taste, not a complete model of every viewing session.

Horizontal shelves include personalized picks, better-rated missing franchise films, movies and new TV series released in the last 90 days, TV with episodes in the last 30 days, preferred genres, and well-rated titles with smaller audiences. Shows already present in Plex are excluded even when their episode coverage is partial. Movie and TV identities remain separate, and the same title appears only once across discovery shelves. Exact TMDB IDs are used where available; library records without them use conservative title/year exclusion, so cross-provider gaps can still require a normal Plex comparison.

The rating filter offers **5.0+, 6.0+, 7.0+, 8.0+, and 9.0+**, defaulting to **6.0/10**, with at least **150 movie votes or 50 TV votes** on TMDB. Recent releases use a smaller vote-count floor (**30 movies / 15 TV**) and display early ratings explicitly. Unrated and low-scoring titles are omitted from ordinary shelves. **Include “so bad it’s good” picks** opts into a separate, clearly labeled set of deliberately low-rated cult picks; low ratings alone do not qualify a film for that row.

Select discoveries and choose **Save picks & compare** to create a local list. Then review missing titles through the existing Radarr/Sonarr flow. This never starts downloads on its own. **Refresh from Plex** bypasses the 20-minute in-memory library snapshot; public TMDB responses retain their normal daily cache.

**Lists & watch orders** combines live Trakt list search, live TMDB collection search, and saved Letterboxd/MDBList/IMDb/ChronoCanon/Trakt lists. Results identify their source and whether they are saved. Other list hosts are not represented as globally searchable APIs: paste a supported URL to preview and compare a new list, or use the import dialog for exports. IMDb can require CSV when automated access is blocked. Full list previews preserve original scope and order and are not filtered by the discovery rating floor.

## Additional metadata providers

**More to explore** combines TMDB genre and keyword discovery with credits from leading cast members, directors, and series creators. Suggestions show their matching reasons, retain separate movie/TV identities, and exclude titles already displayed in other Keep Exploring rows. Ranking balances shared metadata with rating confidence and limits repetition from a single person's filmography. Trakt recommendations remain a fallback; a Trakt connection is not required for broader discovery.

Wikidata and AniList load automatically after the main title information. Expand **Additional title information** in the title header for alternate titles, official links, provider notes, and anime format, source material, episode information, studios, genres, and a separately labeled AniList score. Supplemental data describes the movie or parent show; episode pages identify that scope.

Wikidata uses TMDB's exact Wikidata cross-reference. AniList uses the Wikidata AniList anime identifier. Similar title text never establishes a match. Coverage depends on those cross-references, and anime records may describe a season rather than a whole Plex show. Unmapped connected works link to their provider page instead of being guessed into a Plex/download target.

Provider relationships augment the existing sequel/prequel and franchise sections. Verified local story orders retain priority. Wikidata follows/followed-by orders are explicitly labeled as series order, not guaranteed story chronology. Branches and conflicting orders remain separate connections. Franchise membership, adaptations, shared characters, alternate versions, and recommendations remain distinct. Franchise results are bounded and may be partial; notes identify their sources and limits. Broad Wikidata queries can be rate limited; explicit franchise has-part statements provide a partial fallback.

**TheTVDB** is optional. Under **Settings / Connections → Additional metadata**, enter your project API key and subscriber PIN if your access plan requires it, test, then save. Official TheTVDB lists can establish franchise membership; ordinary custom lists cannot. Access arrangements are described by [TheTVDB](https://www.thetvdb.com/api-information). Keys and PINs remain on the local server and are omitted from browser state responses.

Public responses are cached locally for 24 hours. Additional metadata never marks content watched, adds downloads, or modifies provider accounts. **Retry additional sources** retries failed queries while reusing successful cached responses. A provider outage leaves the main title details and Plex features available.

## Trakt discovery and watch progress

Use **Explore Trakt** to search public lists or browse popular/trending lists. **Preview & compare** reads the complete ranked list and checks Plex without saving or requesting anything. Filter the preview to missing entries, then use **Save full list & compare** to bring it into your workspace. Downloads still use the existing explicit Radarr/Sonarr review flow.

Saved Trakt lists follow source updates by default. Opening Listweavarr checks followed sources at most every six hours; **Check followed lists** checks immediately. Updates are reported for review; **Refresh source** imports them. Toggle **Following source** to stop checks for a list.

**Refresh watched progress** reads the connected Plex account's watch history and shows the next unfinished entry in original source order, plus the next available unwatched entry. Missing files can have unavailable history. Show, season, and episode entries may overlap and count separately. Refresh after watching or changing Plex connections; this feature never marks anything watched.

Title pages show separately labeled Trakt ratings, curated lists containing the movie or parent show, and recommendations. Episode ratings use the exact season and episode. **Upcoming releases** shows the next seven days for titles in followed lists, with Plex availability and Radarr/Sonarr management status. Dates depend on Trakt; a managed series does not imply an episode has downloaded.

These features use your saved public Trakt Client ID. No Trakt account sign-in, client secret, or watch-history synchronization is required.

## Start on Windows

Install Python 3.11 or newer, then double-click **../Start Listweavarr.cmd**, or run:

```powershell
python app.py
```

The app opens at http://127.0.0.1:8765. Keep its terminal open while using it; Ctrl+C stops it. No third-party Python packages are required. It binds only to localhost and does not need to run continuously. Persistent container deployment is available; see DEPLOYMENT.md.

## Connect your NAS

Open **Settings / Connections → Sign in with Plex**. You will go to Plex’s own website to sign in and authorize Listweavarr, then return to the app. Choose your Plex server and click **Connect selected server**. No manual token copying is needed, and Listweavarr never receives your password. The server address and authorized server token are saved automatically after verifying the server identity and library access. Local server connections are preferred. If discovery cannot reach your NAS, expand **Use a specific NAS address**, enter its address, and connect again with the same server selected.

If you return without completing authorization, use **Check sign-in** after finishing on Plex, or start a new sign-in. Pending sign-ins expire after at most 15 minutes. **Find servers** refreshes your server choices. **Disconnect** removes Plex credentials from this local app; you can also revoke Listweavarr under Plex’s Authorized Devices. Changing accounts clears the old selected server. Existing manually configured connections continue to work until you sign in or disconnect, but manual token entry is no longer offered.

For Radarr and Sonarr, enter each service’s NAS URL and API key. **Test connection** uses the current form values without saving them; a blank API key reuses the saved key if available. Click **Save connections** to keep your changes. Keys are in their Settings → General pages. Optionally enter a **TMDB API Read Access Token** (the Bearer token, not the shorter API key) to resolve IMDb episode IDs and check completeness without Sonarr. Credentials stay in `data/state.json`, are not sent back to the browser, and are stored in plaintext on disk: protect that folder. Data is excluded from Git. Remote connections use your chosen HTTP/HTTPS address and normal certificate validation. Plex sign-in requires internet access to plex.tv; library comparisons use the selected server address.

Plex sign-in follows the official [PIN authentication flow](https://forums.plex.tv/t/authenticating-with-plex/609370). Account tokens, server tokens, and pending PIN details are excluded from local browser API responses.

If local DNS blocks Plex's `plex.direct` hostnames, Listweavarr automatically retries local IPv4 addresses encoded in those hostnames. The connection still uses HTTPS with the original hostname for certificate verification and TLS SNI; certificate checks are never disabled. This fallback applies to both connection testing and subsequent library reads.

## Import and compare

Click **Import a list**, paste a public list URL or select a CSV/JSON file, and optionally supply a name. URL imports run in the background with progress; refreshing the browser reconnects to the active import. Imported entries retain their original order. Supported sources:

- **Letterboxd list URLs:** follows every page and resolves film TMDB/IMDb IDs. Per-film IDs are cached locally for seven days. Entries whose IDs cannot be resolved remain visible for correction; they are not silently dropped.
- **MDBList public movie/show URLs:** follows its page-loading endpoint, preserves mixed order, and checks the final entry count against the published total. It refuses incomplete results. Season/episode MDBList entries currently require a structured JSON export.
- **IMDb URLs / CSV:** URL parsing follows exposed next-page links and accepts results only when source positions cover the declared list total completely. Bot checks, pagination gaps, and incomplete structured data produce an error without replacing a saved list. The MCU example currently returns a bot check here; CSV is the reliable fallback. CSV recognizes `Position`, `Const`, `Title`, and `Title Type`, restores numeric position order, and resolves episode IDs with TMDB. Lookup failures retain the entry for review. Repeated titles remain separate ordered entries.
- **Trakt public list URLs:** save your application Client ID under Settings / Connections, then import `/users/name/lists/list-name` or `/lists/123`. Uses the official API with every page verified against the list total, checks unique list-item IDs and complete ranks, sorts by creator rank, and checks whether the list changed during import. Movies, shows, seasons, and episodes retain their own IDs and exact parent-show scope. Public-list reads do not require account sign-in or a client secret when the Client ID has access. Private-list OAuth/PKCE is not implemented.
- **ChronoCanon franchise URLs:** imports ordered movie/TV timelines from public page data. With no timeline parameter, all continuities are included in source watch order. For one continuity, append `?timeline=ash-continuity`, `?timeline=au-movies`, `?timeline=horizons`, or `?timeline=specials` to the Pok?mon URL. Other franchises expose their choices in import notes. No claim is made that separate continuities share one canonical chronology. ChronoCanon currently supplies no exact provider IDs for the Pok?mon sample; movies need an exact match, and broad TV blocks remain unresolved season entries until their intended scope is confirmed. Its internal `dbId` values are never treated as TMDB IDs.
- **CSV / JSON:** JSON may be an array or `{ "items": [...] }`. `../examples/lists/minimal.csv` is a small illustrative excerpt, not a complete chronology.

**Refresh source** reimports a linked URL. Stable source identifiers retain your item corrections and internal IDs. A failed refresh leaves the existing saved list intact. To update an exported list, select the saved list, open **Import a list**, choose the new file, and tick **Update the currently selected list from this file**. This preserves the saved list ID, name, playlist reference, corrections, and manual Plex matches where stable identity is available. A refresh report lists added/removed entries, changed scopes, and order changes; new source entries are labeled. **Compare with Plex** then reports availability changes since the prior comparison. Existing managed playlists are flagged for review when the source changes or their playable contents differ. Recognized fields:

| Field | Meaning |
| --- | --- |
| type | movie, show, season, episode; defaults to movie |
| title | Display title; CSV Name and IMDb Title are recognized |
| year | Optional release year |
| tmdb, tvdb, imdb | IDs of the entry itself |
| show_tmdb, show_tvdb, show_imdb | Parent-show IDs for season/episode entries |
| show_title | Parent show name, useful for grouping |
| season, episode | Nonnegative numbers; required for the corresponding types |

Letterboxd CSV exports initially import as title/year candidates; URL imports include provider IDs. Use **Resolve metadata** after adding a TMDB token to enrich imported IDs, including parent-show TVDB IDs for Sonarr. Exact ID lookups are used; ambiguous title searches are never silently accepted. Numbering follows Plex/Sonarr metadata conventions; anime and alternate orders may need corrections.

**Compare with Plex** reads all movie and TV libraries and uses provider GUIDs. Title/year candidates appear as **Review match**. Click **Correct match** beside an entry to edit metadata IDs, search TMDB and explicitly choose a movie or parent show, or search your Plex catalog and confirm a match. Confirm season/episode numbers separately; a broad story block must not be substituted with a whole show. Season/episode matches select the parent show while retaining episode coordinates. Corrections survive linked-list refreshes. A manual Plex match is restricted to the server where you confirmed it.

Show/season completeness uses aired episode metadata from an existing Sonarr series, or TMDB when configured. Future episodes are excluded and whole-show comparisons exclude specials. Where metadata is unavailable or incomplete, the app keeps **Partial** rather than claiming completeness. Use **Group television** for collapsible show groups; the original list order remains available separately.

## Plex playlists

After comparing, click **Create Plex playlist** and review the item count/title. Confirmed available movies and episodes are included in source order. Shows/seasons expand to their currently available episodes in season/episode order; missing/unmatched entries are omitted. Overlapping show/episode entries can produce repeated episodes, matching the source's structure.

Creation writes in batches and verifies the resulting order. To update a playlist previously created for this list, select **Replace the last playlist created by Listweavarr** in the review. A new playlist is fully created and verified before removing the previous one. Renamed playlists are preserved and require creating a new playlist. This replacement does not carry over playlist playback position. If Plex rejects a batch/order check, the old playlist is preserved and a partial new playlist may remain, with an explicit error. Review in Plex before retrying.

## Request missing items

Click **Add to Radarr** or **Add to Sonarr** beside a missing/partial title to review that one title. To add a batch, tick individual boxes or **Select visible missing**, then use **Add selected** above the list or in the bar that stays visible at the bottom of the screen. Choose the live quality profile and root folder, then **Confirm & search**. Opening the review does not add anything; only confirmation writes to your NAS services and can start downloads through their existing download clients. Listweavarr does not talk to qBittorrent directly.

- Radarr uses a TMDB movie ID or resolves an exact IMDb movie ID through Radarr's own lookup. Existing movies are reused; files already present are skipped.
- Sonarr requires a TVDB show ID (`show_tvdb` for season/episode rows). New shows are added with no episodes monitored, then only missing episodes in the selected scope are monitored and searched. Existing monitoring outside that scope is preserved. Whole-show requests exclude specials; a season-0 or explicit episode request can include them. Sonarr may take time to populate a newly added show's episodes: retry if prompted. Searches can return season packs depending on your Sonarr/indexer configuration.
- Batch results report each success/failure individually. Add/search operations are not transactional. Retry failed items as needed.
- Request/download status is not yet persisted or displayed. Recompare after Plex imports newly downloaded files.

## Browse title information

With TMDB connected, visible list rows automatically load posters, a short synopsis, and a clearly labeled TMDB audience score out of 10. Metadata is cached locally for 24 hours, and fetched in small batches as you scroll rather than blocking on the whole list. Titles without votes show **Not rated**. A metadata failure does not disable requests for confirmed missing items.

TV entries can resolve their parent show using TMDB, TVDB, or IMDb IDs. The episode ID is kept separate from the parent-show ID. In an episode/season row, click the linked show name (or **View full show**) to open the complete show. Whole-show title clicks open this same view. It includes the show poster, synopsis, trailer, and **Your Plex library** coverage for every TMDB season, with expandable episode lists marked In Plex / Missing / Not aired / Unknown. Matching copies across Plex libraries are combined. A possible title-only match must be confirmed before the app treats its coverage as known.

Use **Request missing from whole show** or a season’s request button to review a broader scope than the original list entry. Choose a Sonarr quality profile and destination, then confirm. Coverage is read again at confirmation. Only aired episodes missing from Plex are eligible, and Sonarr files already present are skipped. Whole-show requests exclude specials; a season-0 request can include them. Viewing a show does not add entries to your saved chronology or reorder it. Episode numbering follows TMDB/Plex, so alternate anime or DVD ordering may need manual corrections.

**Sort entries** supports original source order, rating (highest/lowest), title (A–Z/Z–A), release date (newest/oldest), and runtime (shortest/longest). Metadata-based sorts immediately order known values, update after each metadata batch, and show progress until all entries have been checked. Unknown/unrated values stay last in either direction. These sorts change the displayed view only: source ranks and playlist chronology remain intact. Switching lists or refreshing/replacing a list resets the view to source order.

Click a title or poster to open full details: synopsis, release/air date, runtime, genres, status, original language, countries, directors/creators, networks, episode totals where relevant, and cast. **Watch trailer** opens the selected trailer on YouTube. Official trailers are preferred. For seasons/episodes without their own trailer, a parent-show trailer is explicitly labeled **Watch series trailer**. If none is listed by TMDB, the app says so. TMDB and IMDb links are included where available. You can also open the Radarr/Sonarr request review from the details view.

## Current boundaries

No scheduled refresh, Seerr integration, or download progress synchronization yet. IMDb URL parsing is conditional on accessible complete page data; the MCU page is currently bot-blocked, so exported files remain necessary here. ChronoCanon imports require manual matching where provider IDs or exact TV scopes are absent. MDBList season/episode URL entries require a structured export. Long-running work is local to the running process; if the app stops during an import, restart the import. Provider access/layout changes can affect URL imports, so file imports remain available.

## Verification

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
node tests/test_ui.cjs
```

Tests exercise pagination, mixed ordering, correction retention, episode ID resolution, completeness, playlist verification before replacement, Plex authentication/DNS fallback, and download request scope. API mutations in automated tests are mocked. Live download validation requires your configured Radarr/Sonarr services and an explicit item selection in the request review.


### Explore people and related titles

The active list appears at the top of the full-width watch desk. Workspace totals are condensed into an expandable strip. Opening a title or exploring projects uses the main page instead of stacked browsing popups. Back returns to the previous title or project list and preserves your selection. The synopsis appears once; The top information card includes dates, technical details, studios, and series creators. Directors and producers appear in their own clickable portrait row. Cast portraits appear in a horizontal scrolling strip without a fixed cast limit. TV show pages use TMDB aggregate cast and crew across all episodes rather than newest-season credits, and show seasons and episodes appear above related content.

Click cast members, creators, directors, or producers in title details to browse their TMDB movie and TV credits. People pages include a portrait, biographical details, and an expandable biography, followed by selectable project rows with posters, ratings, summaries, and credited roles. Studio / production-company names open the first pages of popular movie and TV projects credited to that company. Search by title or credited role, filter **Both / Movies / TV**, and select individual projects or all visible results. **Save selected & compare with Plex** creates a saved list and checks availability. Use the saved list's existing Add buttons to review missing titles before confirming downloads.

Click a related title or a project title/poster to open that individual title's page without saving it first. **Save title & compare with Plex** adds it to the watch desk so missing items can be reviewed for download. Merely browsing projects or titles does not create lists or submit downloads.

Title details also preview related content. **Browse & select related titles** includes named TMDB movie collections and a separately labeled first page of recommendations. Recommendations do not establish shared-universe membership. TMDB collections may omit television, spin-offs, or other parts of a universe; use curated mixed lists for exhaustive chronological collections. Related results are ordered by release date, not story chronology. Filmographies include guest appearances and crew credits and depend on TMDB completeness.

Cast and director/producer portrait rows rank people with photos first, then episode count descending, then TMDB popularity descending. Movies without episode counts use popularity within each photo group. Episode counts are shown beneath the names; merged crew use their largest director/producer role count rather than adding potentially overlapping episodes.

Episode names in a show's season list open individual episode pages, including specials. These display episode-specific metadata, regular and guest cast, and a link to the full show. Back returns to the previous page. Episodes can be saved individually for Plex comparison and the existing scoped download review.

After a successful confirmed Radarr/Sonarr request, Listweavarr saves that service's last quality profile and destination in local state. These defaults are reused in individual, batch, season, and whole-show reviews across app restarts. Defaults are scoped to the server address; removed profiles or root folders are not preselected.


## Mixed-list verification and refresh workflow

1. Import an IMDb CSV or supported URL; inspect the original source order and any import notes. IMDb explains exports in its [list FAQ](https://help.imdb.com/article/imdb/track-movies-tv/faq-for-the-list-feature/GNQMN47VZSE7KW38). Export access may require signing in or copying the list to your own account.
2. Resolve or explicitly confirm exact IDs and TV scope, then compare with Plex. An unresolved episode or broad TV block is retained for review and cannot be requested as if it were a confirmed missing title.
3. Review missing selections in Radarr/Sonarr; after downloads have been imported into Plex, compare again. Availability changes are shown above the list.
4. Open **Create Plex playlist** and expand its original-order preview to inspect playable items, partial scopes, and omitted entries. Show/season expansion remains at that entry's source position. Plex order is verified, including batches beyond 100 items, before a prior managed playlist can be removed. Playlist fingerprints indicate when an update is needed. Creating or replacing still requires explicit confirmation.
5. Refresh a linked source, or update its exported file in place. Review added/removed/scope/order changes, compare availability, and replace the managed playlist only after reviewing the new plan.

`python scripts/verify_list_workflows.py` performs read-only public-provider and Plex checks using your saved connections. It does not save lists, request downloads, or publish playlists. The IMDb sample is an IMDb-format CSV built from exact live external IDs; it is not a downloaded copy of the blocked full MCU chronology. Automated tests mock playlist and download writes.

`python scripts/verify_trakt.py` reads every page of the saved public Marvel Trakt chronology and compares it with Plex without creating lists, playlists, or downloads. The Trakt Client ID is saved only in local connection state, omitted from browser state responses, and sent only to the fixed official API host; API redirects are rejected.


TV poster overlays use the original SVG status ribbons and optional user-supplied overlay artwork (set `LISTWEAVARR_OVERLAY_DIR`). Show, season and episode posters display their parent series status and network; movies stay plain. TMDB supplies the status and original network (not current streaming availability). ?Airing? indicates a known episode date within three days of today; returning series outside that window use ?Returning.? Ended and cancelled are shown explicitly, and unknown status is never inferred as ended. Multiple-network shows use the first matching supplied network logo, with a network-name fallback when no artwork matches. Metadata loads for visible posters only, coalesces repeat show requests, and uses the existing daily TMDB cache. These layers only affect Listweavarr's display; they do not modify Plex posters or media files.


Use **Ignore title** in saved lists, list previews, project lists, or Explore cards to hide an unwanted title across Listweavarr. Preferences persist in local state; **Lists ? Ignored Titles** lets you restore them. Ignoring a TV show also hides its seasons and episodes; ignoring an individual season or episode stays scoped to that entry. Source lists, playlists and media files are preserved. Explore excludes ignored titles before filling shelves, checking up to five result pages per discovery query when needed; available matches still depend on providers and rating filters.


Recent movie discovery is split into **In theaters** and **Available digitally / on disc**, with a **Release country** selector (Canada by default). The rows use TMDB regional theatrical types 2/3 and digital/physical types 4/5 from the past 90 days. Per-title regional release dates are checked so films already released at home do not remain in the theatrical row. Theater records are not live cinema showtimes; digital includes rentals/purchases and does not promise subscription-streaming availability. Missing regional dates are not guessed from a film's premiere date.

**Track home release** saves a movie to a separate persistent **Release watchlist**. Listweavarr checks that list on startup and every six hours while open, using daily-cached metadata. A persistent in-app notice appears when a tracked regional digital/disc date has arrived, until you dismiss the notice or stop tracking. Open Explore's Release watchlist to see expected dates, check manually, remove entries, or **Save & compare** a released film before reviewing a Radarr request. Existing tracked entries retain their selected country when you change Explore's release country. Checks do not run while Listweavarr is closed; no email/push notification or automatic downloading is enabled.


Explore's **All languages** control lets you save one or more preferred **original languages**, such as English only or English plus French. Open the control, clear All languages, select languages, and choose Apply languages. The full language list comes from TMDB; common languages remain available if that lookup fails. Preferences apply to movie and TV discovery, including personalized suggestions, franchise gaps, recent releases, and cult picks. Discover queries request each selected language individually; returned recommendations are checked again before display. Titles with unknown original language are omitted when preferences are restricted. This filters original production language, not available dubbed audio or subtitles. Saved source lists and the release watchlist are preserved. Choose All languages to restore unrestricted discovery.


Explore also offers **Upcoming movies**, **Upcoming TV**, and **Trending upcoming** for expected releases in the next 180 days. The trending row uses weekly TMDB trending results, filtered to future original release/premiere dates; the other upcoming rows fill from movie/TV discovery and omit titles already in the trending row. Upcoming movie discovery uses the selected release country; TV premiere dates describe the original series premiere, not regional streaming availability. Undated titles are omitted. Dates can change. Upcoming titles without enough audience votes display **Not yet rated** and bypass the rating minimum, while established ratings still obey it. Language, ignore, adult-content and Plex ownership filters remain active.

Upcoming movies support **Track home release**, and upcoming TV supports **Track premiere**. TV tracking stores the media type separately from movies, rechecks the current first-air date, and shows an in-app notice once that premiere date arrives. As with movies, use Save & compare before making any explicit download request. Notifications run only when Listweavarr is opened or left running; future seasons of an existing show are not treated as new-series premieres.


### Comparing ratings

Under **Settings / Connections**, add an optional **MDBList API key** (from https://mdblist.com/preferences/) and test/save it. Extra ratings require this key; TMDB and existing directly fetched Trakt scores continue to work without it. Supported MDBList sources include IMDb, Rotten Tomatoes critics and audience, Metacritic critics and users, Letterboxd, Trakt, MyAnimeList, Roger Ebert, TMDB, and MDBList's aggregate where returned. No score is invented when a source has no coverage.

**All available ratings are shown on title pages by default.** The **Ratings** settings let you select a main source and either keep all title-page scores or check a custom set (including a single source). Compact cards and saved-list rows always show just one preferred score, with an explicitly labeled available fallback if that source is missing. Rating sorts use the selected source and place missing values last; normalized values are used only to sort the same selected source, never to blend critic approval with user averages. Explore's quality minimum remains a TMDB filter and is labeled as such.

Ratings keep native scales: IMDb/TMDB/Trakt out of 10, Letterboxd out of 5, Roger Ebert out of 4, Rotten Tomatoes approval percentages, and Metacritic/MDBList scores out of 100. Votes and provider attribution appear where available. Direct TMDB/Trakt scores take precedence over their MDBList copies. Series scores are never substituted for season or episode scores; those retain exact TMDB and, when fetched, exact Trakt scores. MDBList provides movie/series lookups rather than episode-rating coverage.

Additional ratings load lazily for visible titles and cache locally for 24 hours. Keys remain server-side; cache filenames are hashed and requests use fixed HTTPS endpoints with redirects disabled. Provider failures leave the original metadata usable. Rate/access failures pause extra ratings briefly instead of repeatedly sending failing requests. Refresh the page or save the corrected connection to retry. Coverage, freshness, and API quotas depend on MDBList and its upstream sources. Without a saved key, the settings and fallback display can be used, but live multi-provider scores cannot be verified.


### Workspace protection and recovery (0.4.0)

**Settings ? Backups** includes **Workspace backups**. Download a portable JSON backup, or choose an uploaded/local backup and **Preview restore** before applying it. **Merge** keeps current lists, ignored/tracked items with matching IDs, and existing preferences; **Replace workspace** restores the backed-up workspace while retaining current connection credentials and Plex login. Each restore first creates a safety snapshot. Restored entries are marked unchecked and need Compare with Plex; portable Plex rating keys and playlist associations are not reused. Restore never submits downloads or creates a playlist.

The ten most recent prior workspace versions are automatically retained in `data/backups` when persisted lists or preferences change. These snapshots and portable exports exclude connection settings, login tokens, API keys, caches and session tokens. URL credentials and credential query parameters are removed. Keep `data/state.json` private: that working file still contains your locally saved credentials. Browser-only settings such as entry size remain in that browser. Backup payloads are versioned and validated; the UI supports uploaded files up to 7.5 MB. Save a portable export somewhere other than this computer/NAS for protection against disk failure.

### Following a request

Open **Lists ? Download Progress** to read Radarr/Sonarr status for that list. States distinguish active downloading, waiting for import, import needing attention, imported files awaiting Plex comparison, and availability from the last Plex comparison. Progress badges appear alongside list entries. Select a list or use Refresh progress to update; the visible tab refreshes every 90 seconds, and manager reads cache for up to 60 seconds. Compare with Plex after import to confirm availability. A manager failure is shown as unavailable rather than implying missing content.

Requests made from this version record their submission message and time. Before submitting another search, Listweavarr checks manager files and active queues. Already downloaded/queued movies and exact episodes are skipped; queue-covered episodes are removed from scoped searches. A partially downloading season/show can still request its remaining missing episodes. Queue checks are bounded to 2,000 active records. The panels do not remove torrents, alter queue entries, import files, or manage qBittorrent directly.

### Large lists and release verification

Sorting loads metadata in bounded batches, throttles full-list redraws, and updates final order without navigating away. **Metadata loading** shows failures and a **Retry failed metadata** action. Wrong movie/TV IDs are reported with Correct match guidance rather than silently changing request scope. Original source order remains available and is used for playlist creation regardless of the display sort.

For development/source installs, run `python -m unittest discover -s tests -q` and `node tests/test_ui.cjs`. `python scripts/verify_readiness.py` performs read-only ratings, large-list metadata, and manager-progress checks using saved connections; it writes aggregate results to `data/audits/readiness.json`. `python scripts/verify_list_workflows.py` checks mixed imports, Plex comparison, provider imports and playlist expansion without remote writes. Neither script submits downloads or creates playlists. Live end-to-end write paths are tested with isolated mocks, not by requesting unwanted content from your NAS.

`python build_release.py` creates a runtime ZIP under `releases` with source, UI, required supplied poster-overlay assets, documentation, and a SHA-256 checksum. It excludes state, backups, caches, provider samples and credentials. Extract to a separate folder and run ../Start Listweavarr.cmd after stopping any other copy using port 8765. Tests and development provider fixtures remain in the source workspace rather than the runtime ZIP.

Settings is organized into **Preferences**, **Connections**, and **Backups** tabs. Preferences contains rating sources and their display order, discovery languages, release country, and list entry size. Ignored titles are managed under Lists ? Ignored Titles. Explore keeps per-view discovery filters and links to the shared language/release preferences. Rating selection and display order share one compact list. Each row has a Show checkbox; unchecking a source turns off Show all. The first checked source becomes the preferred compact-card rating when saved.


### Browsing and list organization

**Lists** has **My Lists**, **Official Lists**, **Ignored Titles**, and **Download Progress** tabs. My Lists supports inclusive movie-year filters: leave either end blank for an open range. Movies with unknown years are hidden while a year filter is active; television entries remain visible. These filters change the view, not the source list or playlist order.

**Explore** has **Discover**, **Release Watchlist**, and **Lists & Watch Orders** tabs. Click a discovery shelf heading to open its dedicated poster grid. More provider results load as you scroll, with a Load more button as a fallback. Results continue to respect library ownership, ignored titles, languages, and applicable rating filters. Personalized recommendations, collection gaps, and the cult shelf have finite candidate pools; the page indicates when available matches are exhausted.

**Settings ? Preferences ? Ratings ? Display order** lets you move rating sources up and down with a Show checkbox on each row. The first checked source becomes the preferred compact-card score when saved. Save rating preferences to persist the order. Title pages show selected available sources in that order; compact cards continue to show one preferred score or its labeled fallback.

Official Lists includes four working TMDB movie collections (Star Wars, Harry Potter, Mission: Impossible, and Underworld), previewed in release order before saving. These are movie collections, not complete cross-media universe chronologies. The original watch-order guide directory opens the review-first website/text builder; those guides are not represented as verified bundled timelines.


### Collections and future releases

Explore is the landing page. **Lists ? My Lists** opens a poster catalogue; choose a cover to open its entries. **Create list** starts a local collection. **Edit list & poster** supports renaming, descriptions, image uploads, generated title posters, title searches, whole shows, seasons/episodes, removing entries and changing their order. Edits are staged until Save; a stale editor is rejected if the saved list changed meanwhile.

Linked-source lists retain their link when you rename them or change descriptions/posters. Adding, removing or reordering entries requires the explicit **Convert to local** confirmation and stops source refresh/following. The original source is retained as reference. Source refresh preserves your custom name, description and poster. To link a local/new collection, choose Linked source and a supported public URL; its imported contents replace the local entries. Linking alone does not schedule background imports: Refresh source and existing followed-list checks retain their normal behavior.

Saved poster images are included in portable workspace backups. When creating/replacing a Plex playlist, Listweavarr uploads the list poster and verifies its selection. Poster failures are reported separately from successful playlist creation. Existing Plex playlists are not changed just by editing a local list poster; recreate/replace the playlist to apply it.

Explore's **Save selected picks** routes upcoming titles and movies still in theaters to **Release Watchlist**, and released picks to a saved comparison list. Mixed picks are handled together; no download requests are made by this action. Unknown release dates are retained as pending rather than presented as available.

Release Watchlist displays posters and separate theater, digital and disc dates when reported for your selected country, or the original TV premiere. **Monitor in Radarr/Sonarr** opens a quality/destination review. Confirming enables manager monitoring without an immediate search. Radarr uses minimum availability Released; Sonarr monitors the whole show and future seasons, excluding specials. Existing manager entries retain their destinations and quality profiles. Managers must be running with usable indexers/RSS and quality settings to acquire future releases; monitoring does not guarantee a specific release will be downloaded. Stopping local release tracking does not undo monitoring in your manager.


### Optional indexer discovery and experimental cult picks

Under **Settings ? Connections**, add and test/save an optional Prowlarr URL and API key. Then enable **Popular on my indexers** in Explore. The shelf uses a bounded browse/search sample from your configured indexers, ranks exact movie/show matches by the strongest observed release's seed count, and never sums duplicate releases or submits grabs. It is not a global torrent popularity chart. Indexers that cannot browse without a query may return no results. Unmatched titles are omitted; ordinary rating, language, ignored-title and ownership filters apply. Results cache for 20 minutes; Refresh from Plex also refreshes enabled optional shelves. API keys stay server-side.

**So bad it might be good** is experimental and opt-in. Candidate generation combines keyword discovery and recommendations around known enjoyable-bad examples; these examples are candidate seeds rather than a fixed output list. Scoring requires positive fun evidence: explicit enjoyable-bad tags, sampled review language, or a combination of camp themes, related cult favorites and audience/critic disagreement. Rating alone never qualifies a title. Vote count and release age support confidence; very new, sparsely rated and adult titles are excluded. Smart apostrophes in metadata are normalized. Review evidence counts distinct reviewers and rejects simple negations; it is a phrase-based heuristic, not reliable semantic understanding. Optional MDBList audience/critic data supports a small number of borderline candidates. Scores explain their signals and are not objective quality ratings. Candidate pools are bounded, cache for six hours, and may be small when evidence is sparse.

Both optional shelves load independently after the normal discovery rows, so they do not block the main Explore response. Their headings open the complete current candidate sample, with an explicit end state rather than fabricated endless pagination.

### Requests workspace (first stage of Seerr-style workflows)

**Requests** keeps durable history across saved-list submissions and release monitoring, including failures, pending list-request reviews, scoped movie/show/season/episode identity, timestamps and manager messages. Existing saved request logs are migrated when the workspace is opened. Status filters distinguish monitoring, downloading, import attention, imported files awaiting Plex, failures and confirmed Plex availability. A failed service check preserves the previous status and displays a warning.

**Review / retry** opens current quality profiles and destinations and requires explicit confirmation. Retrying rechecks Plex and the manager rather than blindly submitting the old operation. It does not remove queue entries, force an import or manipulate torrents. Availability transitions create dismissible in-app notices. Checks run at startup and roughly every 90 seconds while the browser remains open and requests are active; the newest 100 unresolved requests are checked per pass. Extra provider results and manager progress are cached separately. This release does not yet provide household logins/permissions, approval queues, external notification agents, multiple manager instances or separate 4K routes. Those are later stages of replacing Seerr, not features implied by this first request-history workspace.


### Single-user requests, manager instances and Discord

**Requests ? Request a title** searches movies and TV without creating a saved list. Choose the exact TV scope, a standard or 4K route, and either an immediate reviewed search or future-release monitoring. You can queue a draft for later approval. Enable **Settings ? Requests ? Queue requests for approval** to defer list submissions, TV scope requests and release monitoring until you approve them. Queued requests make no manager writes. **Review & approve** uses current profiles/destinations and checks ownership and duplicate downloads again. Draft cancellation and declining queued requests affect only local history, never active downloads or files. This remains a single-user local app; household accounts and shared access are not enabled.

**Settings ? Requests ? Manager routes** adds extra Radarr/Sonarr instances. Each has a name, enabled state, standard/4K tier and optional default for that service/tier. Primary instances remain under Connections. Switching manager route in a list/TV/release review reloads that instance's profiles and roots. Requests retain their exact route; status checks and retries use the same instance. Profiles/destinations are remembered separately for each route. Standard and 4K requests have separate identities, and 4K Plex presence requires 4K media attributes rather than just a matching title. Use separate manager instances for separate copies; labeling a route 4K does not configure its quality profile automatically. Disabled routes preserve history but block new submissions and show status warnings. Routes with existing history cannot change service or tier; add a new instance instead.

**Settings ? Notifications ? Discord** accepts an incoming Discord webhook. Notifications default off. Choose events and save to enable; titles, exact scope, library tier and status are sent to the configured channel. **Send test notification** sends a generic test message to your saved webhook. Enabling notifications starts with new events rather than sending old request history. Mention parsing is disabled. Delivery uses a persistent bounded outbox, deduplicates observed events, respects rate-limit cooldowns and retries transient failures with backoff. Permanent failures are reported under notification settings. A process crash after Discord accepted a message but before delivery was recorded can still cause a duplicate on retry.

Status checks and Discord delivery now continue in the local server while it is running, even with the browser closed. Checks are read-only and do not automatically approve or retry requests. Closing the server stops these tasks; Docker/NAS deployment can be considered later for uninterrupted operation. The newest 100 unresolved requests are checked each pass. Browser request-history pages display saved state first while status refreshes separately.

Manager API keys and the Discord webhook remain in local state, are never returned by the configuration APIs and are excluded from portable backups. Backups include request history and the approval preference, but not manager-instance credentials or Discord delivery jobs. Restoring a backup resets the notification cursor to prevent replaying historical events. Restored requests targeting a missing instance require an appropriate route to be configured again before submission; they never silently fall back to the primary manager.


### Sharing a list

Use **Share** on a My Lists catalogue entry, or **Share list** inside the list, to download a versioned `.reelcheck-list.json` file. Send the file through your preferred channel. It includes the collection name, description, optional poster and ordered movie/show/season/episode entries with provider IDs. It excludes source URLs, server paths, Plex keys and availability, watch history, manager/request state and credentials.

The recipient uses **Lists ? My Lists ? Import shared list**, selects the file, previews its title/counts and sample entries, then chooses **Import local copy**. This creates fresh list/item IDs and unchecked availability; compare against the recipient's own Plex server afterward. Imports never request downloads or create playlists. The file format supports up to 10,000 entries and 7.5 MB, preserves unresolved scopes for manual matching, and is validated server-side. Copies are independent; automatic cross-user updates and public hosted sharing links are not implemented.

### Prowlarr matching diagnostics

Prowlarr results often lack TMDB/IMDb IDs, even when the connection is healthy. Optional indexer discovery now deduplicates release variants before checking up to 160 unique candidates. It tries provider IDs first, then cleaned release titles against TMDB. Movie fallback requires an exact title and release year; television uses exact names and first-air years where present. Ambiguous same-title matches, conflicting movie/show results and unresolved entries are excluded. The strongest release seed count is retained per title, not summed across duplicates.

The row reports returned releases, checked candidates, confidently matched titles, and exclusions for existing Plex ownership, language, ignored titles, media type and rating/vote count. Existing preferences remain active; a healthy feed can legitimately have only a few visible titles. Optional discovery still loads separately from the main Explore shelves and caches for 20 minutes. Refresh from Plex clears the optional-source cache for the current check.

### Popular downloads

Explore includes two independent, cached public discovery rows: TorrentFreak?s weekly estimated movie download chart, and EZTV recent releases grouped by show and ranked by the strongest observed seed count across up to 300 releases. EZTV is a sampled ranking, not a worldwide TV chart. Source links appear under About this row. These rows bypass recommendation rating/language thresholds, retain ignored-title exclusions, mark titles already in Plex, and offer a separate Missing only toggle. Prowlarr remains optional. Feed failures are isolated from other Explore rows; a successful chart can be reused for up to 24 hours with an explicit stale-data notice. No torrent URLs are retained or submitted.

### Build a list from a website or pasted text

Use Lists ? My Lists ? Build from website or text (also available inside Import). Public HTTPS articles, list items and tables are extracted into editable text. Remove unrelated sections or alternate orders before inferring entries. The builder recognizes years, S01E01/1x01 scopes and explicit season/episode ranges, preserving candidate order and original source wording. Search TMDB for movie/show suggestions, correct each query/type/year/scope, then explicitly confirm every included entry. No candidate is automatically confirmed; unmatched entries must be corrected or removed. Saving verifies selected identities and TV scopes and creates a local list with unchecked availability. No Plex writes, comparisons or acquisition happen during building.

This is a heuristic parser, not universal language understanding: implicit episode numbering, specials, anime orderings, story blocks, image-only lists and complex tables require manual review. Website fetching does not execute scripts or bypass bot checks; paste the relevant text if access is blocked. Requests only target public HTTPS addresses, validate each redirect and pin the resolved public address. Limits: 5 MB pages, 200,000 text characters and 3,000 inferred entries. Official Lists now links directly to the original guides as builder starting points; these are not presented as verified bundled timelines.

#### Anime and contextual episode ranges

The text builder infers a default parent from typed franchise prefixes (including Pokemon/Pok?mon) or accepts a Default parent show override. Source lines such as `Season 1 Indigo League (Ep 1-69)` remain one editable review entry with first/last episode controls. Confirmed ranges expand into individual episodes only when saved, preserving the placement of intervening movies. Typed movie, special and miniseries labels are cleaned for matching; miniseries do not change the parent for subsequent season lines. Explicit Part 1/Part 2 blocks that restart at episode 1 propose a continuation offset and explain it in the review.

Source numbering and TMDB numbering may differ, particularly for anime. Choose per-season or continuous/absolute numbering globally or on each episode entry. The builder can propose mapping explicit absolute ranges to the single continuous season in a TMDB show; multi-season ambiguities and out-of-bounds ranges require correction. The Pokemon Horizons transition in the supplied format is recognized separately from the original series. Source text stays visible alongside every proposal. No range is silently clipped and no incomplete expanded list is saved. Some specials and story arcs are catalogued within their parent series rather than as separate titles and still require manual matching.

#### British series labels and named specials

`Series 1` is accepted as `Season 1`, including explicit spin-off prefixes and episode ranges. Main bullets are parsed separately from parenthetical prose so references like ?before series 3, episode 6? do not change the entry?s scope. Explicit spin-off prefixes apply to their own bullets; unlabelled main-series bullets keep their original parent. The supplied Doctor Who revival example infers its 2005 parent from the source evidence. Override the default parent with a year, such as `Doctor Who (1963)`, to choose a different series.

Named episode/story entries search the parent?s specials and the current main-series season. Exact metadata title matches, parenthetical aliases, named season arcs and explicitly named multipart extras can propose verified scopes. A new Named episode / story field and scope labels let you correct those proposals. Missing or ambiguous metadata stays reviewable; source instructions about scene edits, optional placements or extra mini-episodes inside season notes are retained as notes and are not automatically expanded into a new watch order.

#### Direct TMDB matching

When name search misses an entry, enter its TMDB ID in the builder row?s optional TMDB ID or URL field, select the media type, and use Find. The retrieved identity remains subject to confirmation. For seasons and episodes use the parent TV show ID with the scope fields, or paste the full TMDB season/episode URL. Official TMDB URLs can infer the media type; numeric IDs require an explicit movie or TV type because those catalogues overlap. IDs override the query/year search without interpreting numeric movie titles as IDs.

The saved-list editor also offers Look up TMDB ID beside Search, using the same input field. Review the fetched title and scope before adding it and saving the list. Existing linked-list detachment rules still apply to membership changes.

#### Multi-season watch-order blocks

Choose Season range in a builder entry and set First season / Last season. A source block such as `Show (seasons 1-4)` stays one review row, checks that every season exists, and expands to four ordered season entries when saved. It does not include later seasons or silently omit missing seasons. The saved-list editor also supports a season range: choose the show, select Season range, set its first/last season, and add the block.

Checkbox bullets, unbalanced title quotes and numeric parenthetical scopes (including `season 3, eps. 1-9`) are recognized. Fully quoted franchise film titles containing colons remain title searches rather than parent/episode splits. Explicit `Show` + quoted pilot/episode labels resolve within the named show. ?The Original Series? is treated as a parent-title alias for matching and ordering, reducing confusion with behind-the-scenes collections. Named episode searches also inspect regular seasons when the selected show has three or fewer seasons. Source wording remains visible, including possible title typos and numbering discrepancies.

Structured episode rows such as `001. Chicago PD - S01E12 - 8:30 PM` keep the title column separate from the episode scope. Times, years and numeric episode titles are not interpreted as range endpoints in this format. Explicit ranges such as `S01E01-E03` remain supported, and reversed ranges have a different error from oversized ranges.

### Delete and update saved lists

My Lists cards and list detail pages offer Delete and Add entries. Delete shows the current list name/count for confirmation and removes only the saved Listweavarr collection. Plex playlists, media files, manager requests and request history are retained. Existing rolling workspace backups can be used to recover a removed list.

Add entries opens the website/text builder with the target list selected. Review and confirm the incoming entries, then choose Append new entries (the default) or Replace entries with this revised order. Append preserves existing order and skips exact duplicate provider IDs and TV scopes by default; turn off duplicate skipping for deliberate repeated entries. Replace uses the complete reviewed order, removing omitted entries while preserving IDs, availability and metadata for matching existing scopes. Both modes retain the saved name, description and artwork, and flag an existing Plex playlist for later review when membership changes. No downloads or Plex writes occur during these operations.

Manual membership changes to a linked list require explicit conversion to local, stopping source updates. To keep the source link, use Refresh source on its card or detail page instead. Existing source refresh keeps local naming/artwork and matching corrections. Stale concurrent changes are rejected; a deleted list is never recreated by an in-flight update.

Public Google Sheets links are supported in the text list builder. Paste the worksheet link and choose Extract source text. All worksheets are imported in workbook tab order by default, including separate yearly tabs. Choose Selected worksheet only to use just the URL gid. Show, Season, Episode and Title columns are recognized, and all proposed matches still require review. Sheets must be publicly readable; otherwise paste the rows. Re-extract the same link with Add entries to append additions or replace the local list with a revised order. This does not create an automatically refreshing linked provider list.

Supported URL and file imports offer source order, title A-Z/Z-A, and year sorting. Season entries can stay separate or combine into whole-show entries (individual episodes remain separate). Combining changes download scope to the whole show, potentially including seasons not in the source. Import options persist on source refreshes and determine saved/playlist order. Trakt app.trakt.tv links are accepted; choose import order explicitly rather than relying on website URL sort parameters.

Official catalogue: the bundled catalogue/official-lists.json contains curated watch orders, posters and descriptions, without credentials, Plex status or request history. Lists support independent A-Z, Z-A, entry-count and recent-update sorting. Opening a bundled list creates an editable personal copy; catalogue upgrades never silently overwrite it. The maintainer can run python publish_catalogue.py --promote-current-lists to rebuild the catalogue from current working lists, preserving stable official IDs and incrementing changed list versions. Original authoring lists retain their history and appear under Official Lists. Runtime release archives include the catalogue. Catalogue updates ship with app releases and can also be reviewed/imported from a public raw JSON link or a catalogue file under Official Lists > Updates > Get catalogue updates.

Dragon Ball Forums chronological guide: the text builder extracts watch-order headings from the opening post, excluding summaries and replies. Pasting the same guide is supported. Choose Original / uncut English dub for 291-episode Dragon Ball Z (the default in the builder), or the older edited 276-episode DUB. The latter preserves bracketed DUB ranges, including single episodes, and flags incompatible TMDB ordering for manual mapping. Daima, GT, Heroes, movies and specials remain separate entries; parenthetical DBS retelling ranges on movies are notes rather than extra episode blocks. Continuous original/uncut ranges automatically split across consecutive TMDB saga seasons, excluding specials. The review shows each translated segment; saving verifies each episode and preserves movie placement between blocks. Edited dub numbering is retained and must be manually mapped when its episode structure differs from TMDB.

Publish an Official List directly in the app: open a saved list and choose Publish as Official List, review the summary, then confirm. For later changes, choose Publish official update. Publishing updates only this list, preserves every other catalogue entry and the working list history, strips private runtime fields, and increments versions only when published content changes. The previous catalogue is backed up as catalogue/official-lists.json.bak. The local official-lists.json is bundled by the release builder; publication does not upload or automatically deliver updates to other installations.

Collection maintenance: Official Lists > Updates reviews newer versions from the installed catalogue. Preserve mode retains personal changes and removals when an original snapshot exists, appends personal additions after official order, and preserves matched Plex/request state. Older copies without a snapshot use a conservative merge that removes nothing. Exact mode adopts the official contents and presentation. Skip hides one version; Undo restores the preceding list, keeping the latest runtime status for matched entries. For catalogue delivery, expand Get catalogue updates to save/check a public raw JSON link or preview a catalogue file before installation. List tools > Check list health opens a collapsed structural report for duplicates, overlaps, episode gaps, invalid scopes and unresolved matches; intentional watch-order gaps are review notes, never automatically corrected. The approved longer-term feature sequence is tracked in FEATURE_ROADMAP.md.

Taste feedback: expand Your taste on a title page to choose More like this, Favorite or Less like this, or clear an existing choice. Episode/season feedback applies to the whole show. Feedback is local, included in workspace backups and managed under Settings > Preferences > Taste & recommendations. Refresh Explore after saving feedback. Personal suggestions use explicit positives, watched titles and high Plex ratings; owning an unwatched, unrated title does not count as liking it. Explicit dislikes exclude that title from personal ranking and weakly reduce similar genre/credited-person matches, while Ignore remains the separate global hiding control. Taste does not change Plex ratings or download anything. Explore card menus show Why this title; titles opened from loaded Explore results also offer a collapsed explanation. Genre matching respects separate movie/TV namespaces. General trend/release charts are not silently converted into personalized rankings.

Explore > Workbench groups advanced discovery into one-tool-at-a-time views: saved recipes and blind spots, Tonight/movie-night shortlist, movie franchise completion, acquisition/storage planning, creator radar, inbox and feedback insights. Existing card selection saves discoveries through the established comparison/release-tracking workflow. Recipe themes use exact TMDB keywords and show warnings when no exact tag exists. Runtime filters for TV refer to episodes. Tonight requires known Plex runtime and availability; it checks next unwatched episodes from up to ten shows. Shortlists are temporary for the current browser session.

List tools > Watch-order paths stores curated routes without reordering the source. Load a path, choose/reorder entries, save, then create a separate viewing list to use the normal playlist/request flow. Essential/chronological paths require curation. Release defaults to known years, then TV scope ordering; it is not exact per-episode release chronology. Paths survive sharing, official publication and source refreshes, with removed IDs omitted when reading a stale path.

List tools > Episode order & editions reads TMDB episode groups (DVD, absolute, story arcs, and other available orders), maps selected source positions to verified normal TMDB episode IDs, and appends only after preview/confirmation. Edited or merged video files still need edition-specific matching; audio language alone does not determine order.

Preferences > Spoiler protection enables conservative hiding until explicit reveal, including watched titles when watch completeness is uncertain. Posters may contain spoilers. Workbench > Feedback insights enables local recommendation logging (off by default), reports correlations and supports confirmed resets. Creator checks and inbox aggregation happen while the app is used; no closed-app scheduler or automatic creator downloads are implied. Storage estimates use your per-item size range and manager-reported free space, not a promised quality-profile file size. All additions are included in workspace backups. See ROADMAP.md for implementation scope and remaining refinements.

Official catalogue delivery: publish list changes, then use Official Lists > Updates > Get catalogue updates > Export catalogue to download official-lists.json. Host that file at a public HTTPS raw JSON URL of your choosing. Recipients save/check that URL or select the file, inspect the proposed new lists and versions, and install explicitly. Installation updates the catalogue only; personal copies use the separate preserve/exact update flow. Sources must be public, credential-free JSON links (not web viewing pages), up to 30 MB. Catalogue versions are stable per list: changed content must be republished at a higher version. Missing local catalogue entries are kept and older remote versions are skipped. This does not automatically upload your catalogue or overwrite personal working lists.

Plex playlist artwork: Edit list & poster > Artwork sent to Plex defaults to the
portrait collection poster. Choose Separate square playlist cover explicitly to
publish that image instead. The other image is used only if the selected shape
has no image. An old generated square cover no longer overrides an uploaded
portrait automatically. The Companion's own portrait/square display setting is
independent of this per-list publication choice.
