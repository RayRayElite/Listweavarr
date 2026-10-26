# Catalogue layout

- bundled/official-lists.json is the redistributable starter catalogue. It contains no embedded artwork, credentials, Plex identifiers, watch state or request history.
- Installed catalogue versions and manifest updates are stored under the runtime data directory, outside the application image, so container upgrades do not reset them.
- Root-level official-lists.json files are ignored legacy developer material. They may contain private/custom artwork and must never be uploaded.

Curator changes are reviewed separately from users' copies and Plex playlists. Before publishing data, verify source attribution and permission for descriptions/artwork. Known reference sites used during curation include Digital Spy, Star Trek Chronology Project, Arrowverse.info, GateWorld, ChronoCanon, public Trakt/Letterboxd/MDBList lists and the user-provided watch-order sources documented in docs/OFFICIAL_AND_COMMUNITY_LISTS.md. Metadata and title IDs do not license the underlying works.
