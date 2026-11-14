# SPDX-License-Identifier: AGPL-3.0-only
"""Optional operator-enabled Plex Home sign-in or owner password recovery.

Password material never enters workspace exports. Opaque session tokens are
stored only as hashes and expire after seven days. Profile-scoped Plex tokens
remain in this private session file, never in browser responses or exports. Logout revokes the session
across restarts. Changing the password file and restarting revokes all sessions.
This is deliberately not a household account system or a public request API.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError

COOKIE = "listweavarr_owner"
LIFETIME = 7 * 86400


class LoginError(ValueError):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


class OwnerAccess:
    def __init__(self, data, password_file=None, plex_id=None):
        password_file = password_file or os.environ.get(
            "LISTWEAVARR_OWNER_PASSWORD_FILE"
        )
        configured_id = Path(data) / "owner-plex-id"
        if plex_id is None:
            plex_id = os.environ.get("LISTWEAVARR_OWNER_PLEX_ID", "")
            if not plex_id and configured_id.exists():
                try:
                    plex_id = configured_id.read_text(encoding="utf-8").strip()
                except OSError:
                    raise ValueError(
                        "Cannot read private owner-plex-id configuration."
                    ) from None
                if not plex_id:
                    raise ValueError(
                        "The private owner-plex-id configuration is empty. Repair it before restarting."
                    )
        self.plex_id = plex_id
        if self.plex_id and (
            not isinstance(self.plex_id, str)
            or not self.plex_id.isascii()
            or not self.plex_id.isdigit()
            or not 1 <= len(self.plex_id) <= 20
            or int(self.plex_id) == 0
        ):
            raise ValueError(
                "LISTWEAVARR_OWNER_PLEX_ID must be the owner's numeric Plex account ID."
            )
        self.password_enabled = bool(password_file)
        self.enabled = bool(password_file or self.plex_id)
        self.lock = threading.RLock()
        self.failures = {}
        self.sessions = {}
        if not self.enabled:
            return
        password = ""
        try:
            if password_file:
                password = (
                    Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
                )
        except OSError:
            raise ValueError(
                "Cannot read LISTWEAVARR_OWNER_PASSWORD_FILE. Check its path and permissions."
            ) from None
        if password_file and (
            not 12 <= len(password) <= 1024
            or not password.strip()
            or any(ord(c) < 32 for c in password)
        ):
            raise ValueError(
                "The owner password file must contain a password of 12 to 1024 characters."
            )
        data = Path(data)
        data.mkdir(parents=True, exist_ok=True)
        key_file = data / "owner-session.key"
        try:
            fd = os.open(key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(secrets.token_hex(32))
        try:
            key = bytes.fromhex(key_file.read_text(encoding="ascii"))
            if len(key) != 32:
                raise ValueError()
        except (OSError, ValueError):
            raise ValueError(
                "The private owner-session.key is damaged. Remove the key and owner-sessions.json together to sign all devices out."
            ) from None
        self.salt = key[:16]
        self.digest = self._digest(password) if password_file else None
        material = password + ("\0plex:" + self.plex_id if self.plex_id else "")
        self.binding = hmac.new(key, material.encode(), hashlib.sha256).hexdigest()
        self.client_id = hmac.new(key, b"plex-owner-client", hashlib.sha256).hexdigest()
        self.file = data / "owner-sessions.json"
        if self.file.exists():
            try:
                saved = json.loads(self.file.read_text(encoding="utf-8"))
                if hmac.compare_digest(saved.get("binding", ""), self.binding):
                    self.sessions = {
                        k: v
                        for k, v in saved.get("sessions", {}).items()
                        if isinstance(k, str) and len(k) == 64 and self.valid(v)
                    }
            except (OSError, ValueError, TypeError, AttributeError):
                raise ValueError(
                    "The private owner-sessions.json is damaged. Remove it to sign all devices out, then restart."
                ) from None
        self._save()

    def _digest(self, value):
        return hashlib.scrypt(
            value.encode("utf-8"),
            salt=self.salt,
            n=16384,
            r=8,
            p=1,
            maxmem=64 * 1024 * 1024,
        )

    def _save(self):
        temporary = self.file.with_suffix(".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"binding": self.binding, "sessions": self.sessions}, stream)
        temporary.replace(self.file)

    def _token(self, cookie):
        try:
            parsed = SimpleCookie()
            parsed.load(cookie or "")
            value = parsed[COOKIE].value if COOKIE in parsed else ""
            return value if len(value) <= 100 else ""
        except CookieError:
            return ""

    def authorized(self, cookie):
        if not self.enabled:
            return True
        token = self._token(cookie)
        if not token:
            return False
        with self.lock:
            return self.valid(
                self.sessions.get(hashlib.sha256(token.encode()).hexdigest(), 0)
            )

    def login(self, password, client):
        if not self.password_enabled:
            raise LoginError("Password sign-in is not enabled.", 400)
        now = time.time()
        with self.lock:
            attempts = [
                stamp for stamp in self.failures.get(client, []) if now - stamp < 300
            ]
            if len(attempts) >= 5:
                raise LoginError(
                    "Too many sign-in attempts. Try again in five minutes.", 429
                )
            valid = False
            if isinstance(password, str) and len(password) <= 1024:
                try:
                    valid = hmac.compare_digest(self._digest(password), self.digest)
                except UnicodeError:
                    pass
            if not valid:
                if len(self.failures) >= 500 and client not in self.failures:
                    self.failures.pop(next(iter(self.failures)))
                self.failures[client] = attempts + [now]
                raise LoginError("The password was not accepted.")
            self.failures.pop(client, None)
            return self.issue()

    @staticmethod
    def expiry(value):
        expiry = value.get("expires", 0) if isinstance(value, dict) else value
        return float(expiry) if type(expiry) in (int, float) else 0

    def valid(self, value):
        if self.expiry(value) <= time.time():
            return False
        if not isinstance(value, dict):
            return type(value) in (int, float)
        if (
            value.get("role") not in ("owner", "member")
            or value.get("account_id") != self.plex_id
        ):
            return False
        identifier = value.get("user_id")
        if (
            not isinstance(identifier, str)
            or not identifier.isascii()
            or not identifier.isdigit()
        ):
            return False
        if (value["role"] == "owner") != (identifier == self.plex_id):
            return False
        return all(
            isinstance(value.get(field), str) and 0 < len(value[field]) <= limit
            for field, limit in (
                ("name", 300),
                ("plex_token", 16000),
                ("client_id", 300),
            )
        )

    def identity(self, cookie):
        if not self.enabled:
            return None
        with self.lock:
            value = self.sessions.get(
                hashlib.sha256(self._token(cookie).encode()).hexdigest()
            )
            if not self.valid(value):
                return None
            if isinstance(value, dict):
                return {key: item for key, item in value.items() if key != "expires"}
            return {
                "role": "owner",
                "user_id": self.plex_id or "owner",
                "name": "Owner",
            }

    def issue(self, identity=None):
        """Mint a local session only after a configured credential is verified."""
        with self.lock:
            now = time.time()
            self.sessions = {
                key: expiry
                for key, expiry in self.sessions.items()
                if self.expiry(expiry) > now
            }
            if len(self.sessions) >= 100:
                self.sessions.pop(
                    min(self.sessions, key=lambda key: self.expiry(self.sessions[key]))
                )
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (
                dict(identity, expires=now + LIFETIME) if identity else now + LIFETIME
            )
            self._save()
            return token

    def logout(self, cookie):
        if self.enabled:
            with self.lock:
                token = self._token(cookie)
                self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
                self._save()


def cookie_header(token="", secure=False):
    return (
        COOKIE
        + "="
        + token
        + "; Path=/; HttpOnly; SameSite=Strict; Max-Age="
        + str(LIFETIME if token else 0)
        + ("; Secure" if secure else "")
    )
