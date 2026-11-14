# SPDX-License-Identifier: AGPL-3.0-only
"""Browser-bound Plex account login followed by verified Plex Home switching.

Tokens stay server-side. Master-account proof alone never grants an owner
session: the selected Home profile (and its PIN, if any) must be verified too.
"""
import hashlib
import secrets
import threading
import time
import urllib.parse
from http.cookies import SimpleCookie, CookieError
import owner_access

COOKIE = "listweavarr_plex_login"


def cookie_header(ticket="", secure=False):
    return (
        f"{COOKIE}={ticket}; Path=/; HttpOnly; SameSite=Strict; Max-Age={900 if ticket else 0}"
        + ("; Secure" if secure else "")
    )


def flag(value):
    return value is True or value in (1, "1", "true")


class PlexOwnerLogin:
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = {}
        self.starts = {}
        self.choices = {}

    def budget(self, records, client, message):
        now = time.time()
        attempts = [stamp for stamp in records.get(client, []) if now - stamp < 300]
        if len(attempts) >= 5:
            raise owner_access.LoginError(message, 429)
        if len(records) >= 500 and client not in records:
            records.pop(next(iter(records)))
        records[client] = attempts + [now]

    def new(self, owner, client):
        if not owner.plex_id:
            raise owner_access.LoginError("Plex sign-in is not enabled.", 400)
        self.budget(
            self.starts, client, "Too many sign-in attempts. Try again in five minutes."
        )
        self.pending = {
            key: value
            for key, value in self.pending.items()
            if value["expires"] > time.time()
        }
        if len(self.pending) >= 100:
            raise owner_access.LoginError("Too many pending sign-ins.", 429)
        ticket = secrets.token_urlsafe(32)
        record = {
            "expires": time.time() + 900,
            "checked": 0,
            "binding": owner.binding,
            "client_id": owner.client_id,
        }
        record["client_id"] = owner.client_id
        self.pending[hashlib.sha256(ticket.encode()).hexdigest()] = record
        return ticket, record

    def start(self, owner, client, request, public_url):
        with self.lock:
            ticket, record = self.new(owner, client)
            pin = request(owner.client_id, "/api/v2/pins", "POST", {"strong": "true"})
            if (
                type(pin.get("id")) is not int
                or pin["id"] < 1
                or not isinstance(pin.get("code"), str)
                or not 6 <= len(pin["code"]) <= 200
            ):
                raise ValueError("Plex returned an invalid sign-in response.")
            lifetime = pin.get("expiresIn", 900)
            if type(lifetime) is not int or lifetime < 1:
                raise ValueError("Plex sign-in expired. Start again.")
            record.update(
                id=pin["id"], code=pin["code"], expires=time.time() + min(lifetime, 900)
            )
            query = urllib.parse.urlencode(
                {
                    "clientID": owner.client_id,
                    "code": pin["code"],
                    "context[device][product]": "Listweavarr",
                    "forwardUrl": public_url.rstrip("/") + "/#owner-plex",
                }
            )
            return ticket, {
                "url": "https://app.plex.tv/auth#?" + query,
                "expires_in": min(lifetime, 900),
            }

    def record(self, owner, cookie):
        try:
            parsed = SimpleCookie()
            parsed.load(cookie or "")
            ticket = parsed[COOKIE].value if COOKIE in parsed else ""
        except CookieError:
            ticket = ""
        if len(ticket) > 100:
            ticket = ""
        key = hashlib.sha256(ticket.encode()).hexdigest()
        record = self.pending.get(key)
        if (
            not record
            or record["expires"] <= time.time()
            or record["binding"] != owner.binding
        ):
            self.pending.pop(key, None)
            raise owner_access.LoginError(
                "This browser's sign-in expired. Start again.", 400
            )
        return key, record

    def home(self, owner, record, token, request):
        account = request(record["client_id"], "/api/v2/user", token=token)
        if (
            str(account.get("id", "")) != owner.plex_id
            or flag(account.get("restricted"))
            or flag(account.get("anonymous"))
        ):
            raise owner_access.LoginError(
                "Sign in with the Plex account configured for this household."
            )
        data = request(record["client_id"], "/api/home/users", token=token)
        if isinstance(data, dict):
            data = data.get("MediaContainer", data)
            data = (
                data.get("User", data.get("users", []))
                if isinstance(data, dict)
                else []
            )
        if not isinstance(data, list) or len(data) > 100:
            raise ValueError("Plex returned an invalid Home profile list.")
        profiles = []
        for row in data:
            identifier = str(row.get("id", ""))
            if not identifier.isdigit() or flag(row.get("guest")):
                continue
            profiles.append(
                {
                    "id": identifier,
                    "uuid": str(row.get("uuid") or identifier),
                    "name": row.get("title") or row.get("username") or "Plex profile",
                    "protected": flag(row.get("protected")),
                }
            )
        if not profiles:
            raise ValueError("No usable Plex Home profiles were returned.")
        record.update(
            master_token=token,
            profiles=profiles,
            account=account.get("username") or account.get("title") or "Plex account",
        )
        return self.info(owner, record)

    def info(self, owner, record):
        return {
            "profiles": [
                {key: row[key] for key in ("id", "name", "protected")}
                for row in record["profiles"]
            ],
            "master": {
                "token": record["master_token"],
                "account_id": owner.plex_id,
                "account": record["account"],
                "client_id": record["client_id"],
            },
        }

    def check(self, owner, cookie, request):
        with self.lock:
            key, record = self.record(owner, cookie)
            if record.get("profiles"):
                return self.info(owner, record)
            if time.time() - record["checked"] < 1:
                return None
            record["checked"] = time.time()
            pin = request(
                owner.client_id,
                "/api/v2/pins/"
                + str(record["id"])
                + "?"
                + urllib.parse.urlencode({"code": record["code"]}),
            )
            if not pin.get("authToken"):
                return None
            try:
                return self.home(owner, record, pin["authToken"], request)
            except owner_access.LoginError:
                self.pending.pop(key, None)
                raise

    def switch_start(self, owner, client, token, request, client_id=None):
        with self.lock:
            ticket, record = self.new(owner, client)
            if client_id:
                record["client_id"] = client_id
            return ticket, self.home(owner, record, token, request)

    def cancel(self, owner, cookie):
        with self.lock:
            try:
                key, _ = self.record(owner, cookie)
            except owner_access.LoginError:
                return
            self.pending.pop(key, None)

    def choose(self, owner, cookie, profile_id, pin, client, request):
        with self.lock:
            key, record = self.record(owner, cookie)
            profile = next(
                (row for row in record.get("profiles", []) if row["id"] == profile_id),
                None,
            )
            if not profile:
                raise owner_access.LoginError(
                    "Choose a profile from this Plex Home.", 400
                )
            if (
                not isinstance(pin, str)
                or len(pin) > 12
                or (pin and not pin.isascii())
                or (pin and not pin.isdigit())
            ):
                raise owner_access.LoginError("Enter the Plex profile PIN.", 400)
            if profile["protected"] or pin:
                self.budget(
                    self.choices,
                    client,
                    "Too many profile attempts. Try again in five minutes.",
                )
            path = (
                "/api/v2/home/users/"
                + urllib.parse.quote(profile["uuid"], safe="")
                + "/switch"
            )
            if pin:
                path += "?" + urllib.parse.urlencode({"pin": pin})
            switched = request(
                record["client_id"], path, "POST", token=record["master_token"]
            )
            switched = switched.get("User", switched.get("user", switched))
            token = switched.get("authToken") if isinstance(switched, dict) else None
            if not token:
                raise owner_access.LoginError("Plex did not authorize that profile.")
            user = request(record["client_id"], "/api/v2/user", token=token)
            if (
                str(user.get("id", "")) != profile["id"]
                or flag(user.get("anonymous"))
                or flag(user.get("guest"))
            ):
                raise owner_access.LoginError(
                    "Plex returned a different profile. No session was created."
                )
            identity = {
                "user_id": profile["id"],
                "account_id": owner.plex_id,
                "name": profile["name"],
                "role": (
                    "owner"
                    if profile["id"] == owner.plex_id
                    and not flag(user.get("restricted"))
                    else "member"
                ),
                "plex_token": token,
                "client_id": record["client_id"],
            }
            session = owner.issue(identity)
            self.pending.pop(key, None)
            return session, identity
