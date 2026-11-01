# SPDX-License-Identifier: AGPL-3.0-only
"""Optional single-owner sign-in, enabled only by an operator password file.

Password material never enters workspace exports. Opaque session tokens are
stored only as hashes and expire after seven days. Logout revokes the session
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
    def __init__(self, data, password_file=None):
        password_file = password_file or os.environ.get(
            "LISTWEAVARR_OWNER_PASSWORD_FILE"
        )
        self.enabled = bool(password_file)
        self.lock = threading.RLock()
        self.failures = {}
        self.sessions = {}
        if not self.enabled:
            return
        try:
            password = Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError:
            raise ValueError(
                "Cannot read LISTWEAVARR_OWNER_PASSWORD_FILE. Check its path and permissions."
            ) from None
        if (
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
        self.digest = self._digest(password)
        self.binding = hmac.new(key, password.encode(), hashlib.sha256).hexdigest()
        self.file = data / "owner-sessions.json"
        if self.file.exists():
            try:
                saved = json.loads(self.file.read_text(encoding="utf-8"))
                if hmac.compare_digest(saved.get("binding", ""), self.binding):
                    self.sessions = {
                        k: float(v)
                        for k, v in saved.get("sessions", {}).items()
                        if isinstance(k, str)
                        and len(k) == 64
                        and isinstance(v, (int, float))
                        and v > time.time()
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
            return (
                self.sessions.get(hashlib.sha256(token.encode()).hexdigest(), 0)
                > time.time()
            )

    def login(self, password, client):
        if not self.enabled:
            raise LoginError("Owner sign-in is not enabled.", 400)
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
            self.sessions = {
                k: expiry for k, expiry in self.sessions.items() if expiry > now
            }
            if len(self.sessions) >= 100:
                self.sessions.pop(min(self.sessions, key=self.sessions.get))
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = now + LIFETIME
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
