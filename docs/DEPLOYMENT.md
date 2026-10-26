# Deployment and upgrades

## Local Python process

Python 3.11+ runs the app without pip dependencies. Start `python app.py` or double-click Start Listweavarr.cmd on Windows. Local defaults bind 127.0.0.1:8765 and open a browser. Credentials and working state stay in data/.

For unattended use, disable browser opening and use a process supervisor appropriate to your OS. Docker Compose below provides restart handling and isolated storage.

## Docker Compose

Install Docker with Compose v2, clone this repository, and run `docker compose up -d --build`. The image runs as non-root UID/GID 10001:10001. Application code is read-only; /config is writable and persistent, and /tmp is temporary. The health endpoint /healthz contains no settings or session token. SIGTERM cleanly shuts down the server.

The default named volume owns the correct permissions. A bind mount is also possible: replace `listweavarr_config:/config` with an absolute host folder and grant UID/GID 10001 write access. Do not solve permissions by running a privileged container or making the directory world-writable. This image does not implement LinuxServer-style PUID/PGID variables.

## NAS or trusted LAN

The app has no login and is single-user. Everyone who can reach its API can act as its user. An explicit Host allowlist/CSRF check is not user authentication.

For access from another device, copy .env.example to .env and configure your actual address, for example:

```dotenv
LISTWEAVARR_PUBLISH_IP=0.0.0.0
LISTWEAVARR_PUBLISH_PORT=8765
LISTWEAVARR_PUBLIC_URL=http://192.168.1.50:8765
LISTWEAVARR_ALLOWED_HOSTS=192.168.1.50:8765,nas.local:8765
```

Then recreate the service with `docker compose up -d --build`. Restrict this port with your firewall to trusted clients. For access over a reverse proxy, use an authenticated TLS proxy, set the public HTTPS origin, and allow that exact host. Wildcard allowed hosts are rejected. Do not expose this service directly on the public Internet.

Inside Docker, `localhost` refers to the container. Configure Plex/Radarr/Sonarr/Prowlarr with reachable LAN DNS/IP or a shared Docker service name. Docker Desktop supports host.docker.internal for host services; Linux Engine needs explicit host-gateway configuration if using that name. Named volumes are private to this app; it does not need direct access to media downloads.

Plex login forwards back to LISTWEAVARR_PUBLIC_URL. Set it before authorizing when using another hostname/port, so the browser returns to the correct origin.

## Environment reference

| Variable | Default / meaning |
|---|---|
| LISTWEAVARR_HOST | 127.0.0.1 locally; 0.0.0.0 in the image |
| LISTWEAVARR_PORT | 8765, the internal listening port |
| LISTWEAVARR_DATA_DIR | data/ locally; /config in the image |
| LISTWEAVARR_PUBLIC_URL | Browser-visible HTTP(S) origin; no path or credentials |
| LISTWEAVARR_ALLOWED_HOSTS | Additional exact host[:port] values, comma separated |
| LISTWEAVARR_OPEN_BROWSER | 1 locally; 0 in Docker |
| LISTWEAVARR_CURATOR_MODE | 0; 1 enables local Official authoring, not hosted identity |
| LISTWEAVARR_OVERLAY_DIR | Optional folder containing status-top-left and network-top-left user assets |
| LISTWEAVARR_PUBLISH_IP | Compose host binding only; defaults to 127.0.0.1 |
| LISTWEAVARR_PUBLISH_PORT | Compose host port only; defaults to 8765 |

Keep internal port 8765 when using the supplied Compose file. Change the published port and public URL for host-side port conflicts. API credentials are entered in Settings, not committed environment files.

## Move an existing local installation into Docker

1. Stop the old app and securely copy its data directory. Preserve the original until the migration is verified.
2. Mount the copy at /config and grant UID/GID 10001 access. Keep state.json, backups, caches and catalogue/ together.
3. If the old installation has catalogue/official-lists.json outside data/, copy it into /config/catalogue/official-lists.json. Keep private posters private.
4. Start the container, verify lists/settings, test provider connections and check Plex availability. Do not submit acquisitions to test the migration.
5. Reauthorize Plex if the callback URL/account/server changed. Keep tokens out of shell history and screenshots.

Legacy v1 reelcheck-* shared-file identifiers and local browser preference keys are retained for compatibility. User-facing branding and current API headers use Listweavarr. The old CSRF header and curator environment variable are accepted during migration. Imported Official versions persist outside the image and override the bundled starter catalogue.

## Backups, upgrades and rollback

Before upgrading, stop the app/container and take a secure full backup of its data directory/volume. It contains plaintext credentials; encrypt and restrict backups. The portable backup UI strips credentials deliberately and cannot restore connections by itself.

Review CHANGELOG, run `git pull --ff-only`, then `docker compose up -d --build`. Rebuilds preserve the config volume. `docker compose down` keeps data; `down -v` deletes it.

Git provides code rollback, not data rollback. To recover a previous application version, check out its tag/commit and rebuild, using a corresponding data backup if a future migration changed the schema. Do not overwrite newer personal state blindly. Prefer a new recovery branch over resetting shared main history.

## Build validation

CI builds a real Linux image, starts it with a clean named volume and read-only root filesystem, checks Host protection and the health/UI endpoints, creates a synthetic empty list, restarts the container and verifies persistence. Local Windows checks cover the same Python/client logic. If Docker is not installed locally, do not claim a local container run; use the recorded CI result.
