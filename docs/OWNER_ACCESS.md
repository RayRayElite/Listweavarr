# Single-owner access

Owner sign-in is optional and off by default. Existing localhost installations
continue to work as before. This protects one operator workspace; household
accounts, delegated roles and a public request API are separate future features.

## Enable locally

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
Its value must be a path **inside the container**. Mount a private file read-only
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
hashed session registry, so sessions survive container restarts. Run one server
process per data directory. No extra Python packages or account service is needed.

## Sessions and recovery

Sessions expire after seven days. Cookies are HttpOnly and SameSite=Strict;
`Secure` is added when `LISTWEAVARR_PUBLIC_URL` is HTTPS. Use HTTPS for access
outside the local machine and configure that public URL to match your browser's
origin. The built-in HTTP listener does not terminate TLS; keep using a private
network or appropriate reverse proxy. Sign-in adds owner authentication; it does
not turn the tool into a public multi-user service.

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
- **Return to trusted local mode:** stop the server, unset the password-file
  variable, and restart on the intended restricted interface.

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
