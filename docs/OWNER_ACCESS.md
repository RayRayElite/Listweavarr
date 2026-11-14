# Plex Home and owner access

Access protection remains optional until an operator enables it. A single Plex
account sign-in is followed by a Plex Home profile chooser; protected profiles
require their Plex PIN. The verified selected profile supplies library access
and personal history. It does not require another login under Connections.

## Enable from the app

1. Connect the household's primary Plex account under Settings > Connections.
2. Open Settings > Access and select **Find connected Plex account ID**.
3. Review the account, select **Enable Plex household sign-in**, and confirm.
4. Choose the desired Home profile. Existing lists stay in the owner workspace;
   household members start with their own personal workspace. Official Lists
   remain shared.

This is an explicit installation-administrator action in the existing local
access mode. It is not an anonymous first-login claim flow. Configure access
before exposing an installation to other networks. The enabling browser retains
an owner setup session so it can complete the profile selection.

The choice persists in private `data/owner-plex-id` (Docker: `/config/owner-plex-id`).
Operators may instead set `LISTWEAVARR_OWNER_PLEX_ID` to the numeric primary Plex
account ID. The environment value takes precedence. A username/email is not an
account ID. Changing this identity and restarting revokes existing app sessions.

## Profile behavior

See [Plex Home profiles](PLEX_HOME_PROFILES.md) for isolation, permissions and
current limits. Profile switching is available beside Search. All Home profile
switches are validated by Plex; the app does not store or bypass Home PINs.
Server/library discovery uses that profile's authorization. An unavailable
library never falls back to the owner's token.

## Optional owner password fallback

1. Put a strong password of 12 to 1024 characters in a private UTF-8 text file
   outside the public source tree, for example inside your ignored data folder.
   A final newline is allowed. Restrict the file to the account running Listweavarr.
2. Set `LISTWEAVARR_OWNER_PASSWORD_FILE` to that file's absolute path in the
   environment used to launch the app, then restart Listweavarr.
3. Open the usual app URL and sign in. **Settings > Access** shows the active mode
   and lets you sign this browser out. Enabling sign-in does not alter Plex login,
   list contents, integration credentials or download settings.

For example, launch from PowerShell after creating the private file:

```powershell
$env:LISTWEAVARR_OWNER_PASSWORD_FILE = 'D:\private-config\owner-password'
python app.py
```

The variable belongs to the process/supervisor launching the server. It is not a
service API key and does not belong in a published list or repository.

## Docker

The supplied Compose environment passes through `LISTWEAVARR_OWNER_PASSWORD_FILE`.
Its value must be a path **inside the container**. Plex Home sign-in may also be
configured using `LISTWEAVARR_OWNER_PLEX_ID` without a password file. Mount a private file read-only
at that path and make it readable by UID 10001. For example, add a Compose override:

```yaml
services:
  listweavarr:
    environment:
      LISTWEAVARR_OWNER_PASSWORD_FILE: /run/secrets/listweavarr_owner_password
    secrets:
      - listweavarr_owner_password
secrets:
  listweavarr_owner_password:
    file: /absolute/private/path/owner-password
```

Keep `/config` writable and persistent. It holds the private session key and
private session registry (including scoped Plex credentials), so sessions survive container restarts. Run one server
process per data directory. No extra Python packages or account service is needed.

## Sessions and recovery

Sessions expire after seven days. Cookies are HttpOnly and SameSite=Strict;
`Secure` is added when `LISTWEAVARR_PUBLIC_URL` is HTTPS. Use HTTPS for access
outside the local machine and configure that public URL to match your browser's
origin. The built-in HTTP listener does not terminate TLS; keep using a private
network or appropriate reverse proxy. Sign-in protects the installation and its household workspaces; this is not
a public registration service.

Failed sign-in attempts are limited to five per connection IP within five
minutes. Forwarded IP headers are not trusted, so a proxy may share a rate-limit
bucket. Recovery requires access to the installation, not an email service:

- **Forgot/change password:** replace the password file and restart. All existing
  sessions are revoked. Lists and connections are preserved.
- **Sign out one browser:** use Settings > Access. Its session is revoked in the
  server registry, including after a restart.
- **Sign out every device:** stop the server and remove `owner-sessions.json`
  from the data directory, then restart. Keep the configured password file.
- **Damaged session key:** stop the server, remove `owner-session.key` and
  `owner-sessions.json` together, then restart to create a new key and sign in.
- **Return to trusted local mode:** stop the server, unset the password-file and Plex-owner
  variables, remove the private owner-plex-id file if present, and restart on the intended restricted interface.

Owner credentials/session files are not part of portable workspace backups or
source releases. Backing up the private deployment directory yourself remains an
operator decision. Never share the password file, key or session registry.

## Plex Companion

Paired Companion endpoints retain their own scoped bearer-token authorization;
they do not need a browser login cookie. Pairing management still requires owner
sign-in and the normal CSRF token. Revoking an owner session does not silently
revoke Companion pairings; use the existing pairing-revocation control for that.
Health checks and static scripts remain public; state, jobs and normal API
operations require a valid owner session when this mode is enabled.


## Recover a Plex-only installation

The local operator can remove `data/owner-plex-id`, unset
`LISTWEAVARR_OWNER_PLEX_ID`, and restart to return to local mode. Keep the data
directory private; this is a local deployment recovery action, not an HTTP API.
If a password file remains configured, password protection remains enabled.
Plex outages prevent fresh Plex authorization/profile switching; valid local
sessions continue until expiry and an optional password fallback remains usable.

Protocol references: [Plex developer authentication](https://developer.plex.tv/pms/)
and [Plex Home switching](https://support.plex.tv/articles/204232453-fast-user-switching/).
