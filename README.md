# Listweavarr

**Weave your next watch.** Curated lists, connected stories, and a library worth exploring.

[![CI](https://github.com/RayRayElite/Listweavarr/actions/workflows/ci.yml/badge.svg)](https://github.com/RayRayElite/Listweavarr/actions/workflows/ci.yml)
[![License: AGPLv3](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)

Listweavarr is a single-user, self-hosted movie and TV discovery workbench built around **lists and watch orders**. Import a franchise timeline, match movies/seasons/episodes, compare it with Plex, discover what is missing, and create an ordered Plex playlist. Requests to Radarr and Sonarr are explicitly reviewed.

## What it does

- Import supported Trakt, Letterboxd, MDBList, IMDb and ChronoCanon lists, files, text, articles and public Google Sheets.
- Review inferred matches before saving; correct IDs, episode ranges, anime numbering and mixed movie/TV sequences.
- Keep local collections or follow linked sources; curate multiple watch orders and share portable list files.
- Explore recommendations informed by your Plex library, personal ratings and watch history, with ignore, language and release filters.
- Track upcoming releases, creator projects, requested downloads and availability notices.
- Build Favorites from Plex, plan Tonight sessions and find franchise/library gaps.
- Create Plex playlists with independent square covers. Preview Official catalogue updates separately from personal-copy and Plex updates.

**Public community hosting is not deployed.** File sharing works today. Curator mode prepares local Official versions; actual shared publishing requires a separately managed repository/service.

## Run locally

Requires **Python 3.11+**. No pip packages, Node or database server are needed at runtime.

```sh
git clone https://github.com/RayRayElite/Listweavarr.git
cd Listweavarr
python app.py
```

Open **http://127.0.0.1:8765**. Windows users can double-click **Start Listweavarr.cmd**. Keep the process running; Ctrl+C stops it. Settings, credentials, lists and caches are stored in `data/`, which is excluded from Git.

Connect Plex and TMDB in **Settings ? Connections**. Optional integrations include Radarr, Sonarr, Trakt, MDBList, TheTVDB, Prowlarr and Discord. Use API credentials issued to you; no shared credentials are bundled. Some discovery and metadata features require their provider connection.

## Run persistently with Docker

Requires Docker Engine/Desktop with Compose v2. From the repository directory:

```sh
docker compose up -d --build
docker compose logs -f
```

Open **http://127.0.0.1:8765**. The named volume `listweavarr_config` persists settings, caches, lists and installed catalogue updates at `/config`. The container runs as UID/GID `10001:10001`, has a read-only application filesystem and restarts unless stopped.

```sh
# Update after reviewing the changelog and backing up the config volume:
git pull --ff-only
docker compose up -d --build
# Stop without deleting saved data:
docker compose down
```

Do not use `docker compose down -v` unless you intend to delete the saved volume. This release builds its image from source; it does not require a Docker registry account.

For NAS/LAN deployment, custom ports, migration from a local installation and backups, see **[Deployment](docs/DEPLOYMENT.md)**. Container connections to Plex/Radarr/Sonarr need reachable NAS/service addresses; `localhost` inside the container means the container itself.

## Access and privacy

Listweavarr is currently **single-user and has no application login**. Default local and Compose configurations expose it only to localhost. Configured LAN access must be restricted to trusted users. Do not expose it directly to the Internet; use an authenticated reverse proxy or private network. Host allowlisting and CSRF tokens are browser-request protections, not user authentication.

Credentials stay in the server-side state file and are omitted from ordinary browser state responses and portable backups. Protect the data directory and volume: it contains credentials in plaintext. Do not publish it, an exported credential backup, logs containing provider responses, or screenshots of your private library.

## Artwork and metadata

Third-party posters and Kometa/logo collections are **not bundled** without redistribution permission. Users may add their own images. Original SVG status ribbons are included; provider artwork is loaded from TMDB when configured. Movie/TV names and artwork remain the property of their respective owners.

Metadata and ratings: [TMDB](https://www.themoviedb.org/), with optional provider integrations. This product uses the TMDB API but is not endorsed or certified by TMDB. See [Third-party notices](THIRD_PARTY_NOTICES.md).

## Documentation and contributions

- [User guide](docs/USER_GUIDE.md) ? [Deployment](docs/DEPLOYMENT.md) ? [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) ? [Architecture and code map](docs/CODE_MAP.md) ? [Security](SECURITY.md)
- [Official/Community publishing design](docs/OFFICIAL_AND_COMMUNITY_LISTS.md) ? [Roadmap](docs/ROADMAP.md)
- [Example CSV](examples/lists/minimal.csv)

Development checks (Node 22+ is only needed for the client regression harness):

```sh
python -m unittest discover -s tests -q
node tests/test_ui.cjs
python scripts/check_frontend.py
python scripts/check_release.py
python scripts/build_release.py
```

## License

Copyright (c) 2026 RayRayElite and contributors. Source code is licensed **AGPL-3.0-only**; see [LICENSE](LICENSE). Modified network-served versions must meet AGPL source-availability requirements. Provider data, names and third-party artwork have their own rights and are not relicensed by this project's code license.
