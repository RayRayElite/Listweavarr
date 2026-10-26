# Security policy

Listweavarr is a trusted single-user application. It has no user authentication, and API state is accessible to anyone who can reach an allowed host. Default configurations bind/publish only to localhost. Use an authenticated proxy/private network for remote access; never publish the port directly to the Internet.

API mutations require the session CSRF token and an explicit Host allowlist. These controls resist cross-site requests and DNS rebinding; they do not authenticate a person. Public URL configuration must be an explicit origin. Curator mode is a local authoring switch, not remote curator identity.

The persistent data directory contains plaintext integration credentials. Restrict filesystem access, back it up securely and never attach it to an issue. Portable application backups intentionally remove credentials and therefore are not a substitute for an encrypted full-data backup.

For vulnerabilities, avoid posting credentials, exploit details or private state publicly. Contact the maintainer through GitHub Security Advisories/private reporting when available. If private reporting is unavailable, open an issue asking for a private contact without disclosing the vulnerability. Include affected version, impact and minimal reproduction privately.

Current releases receive fixes on main. This is an early public release, not a promise of Internet-facing hardening or a multi-user security boundary.
