# Plex Home profiles

One household Plex account can authorize Listweavarr. Each browser then selects
a verified Plex Home profile. The configured primary account is the installation
owner; other non-guest Home profiles are members. Plex validates each switch and
any required profile PIN. There is no locally invented profile-password system.

## What is separate

- Plex library reads and watched history use the selected profile's own token.
- Each member has private lists, comparisons, watched snapshots, preferences,
  ignored titles, release tracking, creator follows, taste and smart-list results.
- Import jobs retain their originating context and cannot be polled by another
  profile. Provider library caches include the profile-specific server token.
- Existing owner lists and history are preserved. They are not copied into
  members' workspaces. Use explicit list sharing/Official Lists to share curation.
- Companion resume positions and pins already use Plex server/profile/playlist
  identities. Main-app profile switching does not merge those identities.

Member state lives in `data/profiles/<hashed-account-and-profile>/state.json`.
Provider metadata settings are inherited read-only; manager credentials are not.
Tokens remain in private session/connection files, never browser storage or list
exports. Back up the whole private data directory to preserve all household data.
The workspace backup UI still operates on the owner workspace only.

## Permissions and current limits

The owner manages service connections, downloads/requests, notifications, backups,
curator publishing and maintenance. Members can discover, curate personal lists,
check their accessible Plex media and publish their own Plex playlists. Unknown
member mutations fail closed. Household download approvals and member scheduled
jobs/notifications are separate follow-ups; this increment does not grant those
administrative actions to family profiles. Guest/anonymous accounts are excluded.

Shared server selection is reused only after obtaining and testing the selected
profile's own server token. If that server is not accessible, Connections lets
the profile discover its available servers. It never borrows the owner token.
The listed libraries are those returned by Plex for the selected profile.

App sessions last seven days and survive restarts. Logout revokes the local
session and any pending profile selection. Profile PIN attempts and account
starts are rate-limited. Correct clocks and private data-directory permissions
remain operator responsibilities. Normal Plex sessions/history are not modified
by signing in, choosing a profile or reading availability.

## Implementation map

- `owner_access.py`: hashed app sessions, credential binding and password recovery.
- `plex_owner.py`: browser-bound account PIN, Home enumeration, PIN switch and
  independent user-info verification before session creation.
- `profile_workspace.py`: request context, safe private path, read-only shared
  providers, and the member mutation allowlist.
- `app.py`: sets/resets context for each HTTP request and copies import-job context.
- `tests/test_plex_home_access.py`: end-to-end setup/login and isolation boundaries.

No profile gate is enabled merely by installing an update. Enable explicitly in
Settings > Access or through operator environment configuration.
