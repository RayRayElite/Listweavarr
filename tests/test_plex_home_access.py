# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import app
import owner_access
import snapshot_cache
import plex_owner
import profile_workspace as workspace


class PlexHomeAccessTests(unittest.TestCase):
    def fixture(self, folder):
        owner = owner_access.OwnerAccess(Path(folder) / "private", plex_id="42")
        flow = plex_owner.PlexOwnerLogin()
        calls = []

        def request(client, path, method="GET", fields=None, token=None):
            calls.append((path, method, token))
            if path == "/api/v2/pins":
                return {"id": 1, "code": "strong-code", "expiresIn": 900}
            if path.startswith("/api/v2/pins/"):
                return {"authToken": "master"}
            if path == "/api/v2/user":
                return {
                    "id": 9 if token == "child" else 42,
                    "username": "Owner",
                    "restricted": token == "child",
                }
            if path == "/api/home/users":
                return {
                    "MediaContainer": {
                        "User": [
                            {
                                "id": 42,
                                "uuid": "owner-uuid",
                                "title": "Owner",
                                "protected": True,
                            },
                            {
                                "id": 9,
                                "uuid": "child-uuid",
                                "title": "Gregg",
                                "restricted": True,
                            },
                        ]
                    }
                }
            if "/switch" in path:
                if "owner-uuid" in path and "pin=1234" not in path:
                    raise ValueError("PIN rejected")
                return {"authToken": "child" if "child-uuid" in path else "master"}
            raise AssertionError(path)

        return owner, flow, request, calls

    def test_malformed_or_cross_household_sessions_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, flow, request, calls = self.fixture(folder)
            identity = {
                "role": "member",
                "account_id": "42",
                "user_id": "9",
                "name": "Gregg",
                "plex_token": "child",
                "client_id": "client",
            }
            session = owner.issue(identity)
            cookie = owner_access.cookie_header(session)
            import hashlib

            key = hashlib.sha256(session.encode()).hexdigest()
            good = copy.deepcopy(owner.sessions[key])
            for changes in (
                {"role": "owner"},
                {"account_id": "other"},
                {"plex_token": ""},
                {"user_id": None},
            ):
                owner.sessions[key] = dict(good, **changes)
                self.assertFalse(owner.authorized(cookie))
                self.assertIsNone(owner.identity(cookie))
            owner.sessions[key] = good
            self.assertTrue(owner.authorized(cookie))

    def test_legacy_home_xml_is_accepted_without_guessing_other_endpoints(self):
        parsed = app.decode_plex_account(
            "/api/home/users",
            b'<MediaContainer><User id="9" title="Gregg" restricted="1" protected="0"/></MediaContainer>',
        )
        self.assertEqual(parsed["User"][0]["id"], "9")
        self.assertEqual(
            app.decode_plex_account(
                "/api/v2/home/users/uuid/switch", b'<user id="9" authToken="private"/>'
            )["User"]["id"],
            "9",
        )
        with self.assertRaises(ValueError):
            app.decode_plex_account("/api/v2/user", b"<html>invalid</html>")

    def test_account_login_requires_verified_profile_and_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, flow, request, calls = self.fixture(folder)
            ticket, result = flow.start(
                owner, "client", request, "http://localhost:8765"
            )
            self.assertTrue(result["url"].startswith("https://app.plex.tv/auth#?"))
            cookie = plex_owner.cookie_header(ticket)
            profiles = flow.check(owner, cookie, request)
            self.assertEqual(len(profiles["profiles"]), 2)
            self.assertEqual(
                owner.sessions, {}, "Master account proof must not bypass Home PIN"
            )
            with self.assertRaises(ValueError):
                flow.choose(owner, cookie, "42", "wrong", "client", request)
            with self.assertRaises(ValueError):
                flow.choose(owner, cookie, "42", "0000", "client", request)
            self.assertEqual(owner.sessions, {})
            session, user = flow.choose(owner, cookie, "42", "1234", "client", request)
            self.assertEqual(user["role"], "owner")
            self.assertTrue(owner.authorized(owner_access.cookie_header(session)))
            with self.assertRaises(ValueError):
                flow.choose(owner, cookie, "9", "", "client", request)

    def test_managed_profile_has_separate_identity_and_server_side_credential(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, flow, request, calls = self.fixture(folder)
            ticket, _ = flow.start(owner, "client", request, "http://localhost:8765")
            cookie = plex_owner.cookie_header(ticket)
            flow.check(owner, cookie, request)
            with self.assertRaises(ValueError):
                flow.choose(
                    owner,
                    plex_owner.cookie_header("other-browser"),
                    "9",
                    "",
                    "client",
                    request,
                )
            with self.assertRaises(ValueError):
                flow.choose(owner, cookie, "999", "", "client", request)
            session, user = flow.choose(owner, cookie, "9", "", "client", request)
            self.assertEqual(user["role"], "member")
            self.assertEqual(user["plex_token"], "child")
            restored = owner_access.OwnerAccess(Path(folder) / "private", plex_id="42")
            identity = restored.identity(owner_access.cookie_header(session))
            self.assertEqual(identity["user_id"], "9")
            self.assertEqual(identity["plex_token"], "child")
            self.assertNotIn(
                session, (Path(folder) / "private/owner-sessions.json").read_text()
            )

    def test_wrong_household_or_profile_token_cannot_create_session(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, flow, request, calls = self.fixture(folder)
            ticket, _ = flow.start(owner, "client", request, "http://localhost:8765")
            cookie = plex_owner.cookie_header(ticket)

            def other(*args, **kwargs):
                if args[1] == "/api/v2/user":
                    return {"id": 99}
                return request(*args, **kwargs)

            with self.assertRaises(ValueError):
                flow.check(owner, cookie, other)
            self.assertEqual(owner.sessions, {})
            ticket, _ = flow.start(owner, "client", request, "http://localhost:8765")
            cookie = plex_owner.cookie_header(ticket)
            flow.check(owner, cookie, request)

            def wrong_profile(*args, **kwargs):
                if args[1] == "/api/v2/user" and kwargs.get("token") == "child":
                    return {"id": 42}
                return request(*args, **kwargs)

            with self.assertRaises(ValueError):
                flow.choose(owner, cookie, "9", "", "client", wrong_profile)
            self.assertEqual(owner.sessions, {})

    def test_profile_state_and_background_context_do_not_mix(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            root = {
                "settings": {
                    "tmdb": {"key": "shared-metadata"},
                    "radarr": {"key": "owner-only"},
                    "plex": {"url": "http://plex", "key": "owner-token"},
                },
                "lists": [{"id": "owner-list", "name": "Owner", "items": []}],
                "taste_feedback": {"owner": "like"},
            }
            app.save_state(root, backup=False)
            first = {
                "role": "member",
                "account_id": "42",
                "user_id": "9",
                "name": "Gregg",
                "plex_token": "child",
                "client_id": "client",
            }
            second = dict(first, user_id="10", name="Other", plex_token="other-token")
            with workspace.use(first):
                state = app.read_state()
                self.assertEqual(state["lists"], [])
                self.assertNotIn("radarr", state["settings"])
                self.assertNotIn("plex", state["settings"])
                self.assertEqual(state["plex_auth"]["token"], "child")
                state["taste_feedback"] = {"gregg": "like"}
                app.save_state(state, backup=False)
                stored = json.loads(
                    (workspace.directory(Path(folder)) / "state.json").read_text()
                )
                self.assertNotIn("tmdb", stored["settings"])
                self.assertNotIn("plex_auth", stored)
            with workspace.use(second):
                self.assertNotIn("taste_feedback", app.read_state())
            with workspace.use(first):
                self.assertEqual(app.read_state()["taste_feedback"], {"gregg": "like"})
            self.assertEqual(app.read_state(), root)

    def test_member_http_boundaries_and_job_visibility(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            owner = owner_access.OwnerAccess(Path(folder) / "private", plex_id="42")
            identity = {
                "role": "member",
                "account_id": "42",
                "user_id": "9",
                "name": "Gregg",
                "plex_token": "child",
                "client_id": "client",
            }
            token = owner.issue(identity)
            cookie = owner_access.cookie_header(token)
            app.save_state(
                {
                    "settings": {"radarr": {"key": "owner-secret"}},
                    "lists": [
                        {"id": "owner", "name": "Private owner list", "items": []}
                    ],
                },
                backup=False,
            )
            with patch.object(app, "OWNER", owner), patch.object(
                app, "JOBS", {"owner-job": {"status": "done", "profile_scope": "owner"}}
            ):
                server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()

                def read(path, body=None):
                    headers = {
                        "Host": "127.0.0.1:8765",
                        "Cookie": cookie,
                        "X-Listweavarr-Token": app.SESSION,
                    }
                    if body is not None:
                        headers["Content-Type"] = "application/json"
                    return urllib.request.urlopen(
                        urllib.request.Request(
                            f"http://127.0.0.1:{server.server_port}" + path,
                            data=(
                                json.dumps(body).encode() if body is not None else None
                            ),
                            headers=headers,
                        )
                    )

                try:
                    with read("/api/state") as response:
                        data = json.load(response)
                    self.assertEqual(data["lists"], [])
                    self.assertEqual(data["active_profile"]["user_id"], "9")
                    self.assertNotIn("radarr", data["settings"])
                    self.assertNotIn("child", json.dumps(data))
                    for path in (
                        "/api/settings",
                        "/api/requests/create",
                        "/api/playlist-companion/pair",
                        "/api/backup/restore",
                    ):
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            read(path, {})
                        self.assertEqual(error.exception.code, 403)
                        error.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        read("/api/job?id=owner-job")
                    self.assertEqual(error.exception.code, 404)
                    error.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()

    def test_shared_settings_projection_never_copies_owner_personal_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "settings": {"tmdb": {"key": "shared"}},
                        "lists": [{"name": "Private"}],
                    }
                )
            )
            projected = snapshot_cache.read(path, {}, fields=("settings",))
            self.assertNotIn("lists", projected)
            projected["settings"]["tmdb"]["key"] = "changed"
            self.assertEqual(
                snapshot_cache.read(path, {}, fields=("settings",))["settings"]["tmdb"][
                    "key"
                ],
                "shared",
            )

    def test_connection_bootstrap_never_reuses_owner_token(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            app, "DATA", Path(folder)
        ):
            root = {
                "settings": {
                    "plex": {
                        "url": "http://plex",
                        "key": "owner-key",
                        "server_id": "server",
                    }
                },
                "lists": [],
            }
            app.save_state(root, backup=False)
            identity = {
                "role": "member",
                "account_id": "42",
                "user_id": "9",
                "name": "Gregg",
                "plex_token": "child",
                "client_id": "client",
            }

            def unavailable(state, server):
                self.assertEqual(state["plex_auth"]["token"], "child")
                self.assertNotIn("plex", state["settings"])
                raise ValueError("Not shared")

            with patch.object(app, "connect_plex_server", side_effect=unavailable):
                self.assertFalse(app.prepare_profile_workspace(identity))
            with workspace.use(identity):
                self.assertNotIn("plex", app.read_state()["settings"])
            self.assertEqual(app.read_state(), root)


class HouseholdHTTPFlowTests(unittest.TestCase):
    def test_login_profile_selection_and_explicit_operator_enable(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            app, "DATA", Path(folder)
        ), patch.dict("os.environ", {}, clear=True):
            local = owner_access.OwnerAccess(Path(folder))
            root = {
                "settings": {},
                "lists": [{"id": "owner", "name": "Owner list", "items": []}],
                "plex_auth": {"token": "master", "client_id": "client"},
            }
            app.save_state(root, backup=False)

            def request(client, path, method="GET", fields=None, token=None):
                if path == "/api/v2/pins":
                    return {"id": 1, "code": "strong-code", "expiresIn": 900}
                if path.startswith("/api/v2/pins/"):
                    return {"authToken": "master"}
                if path == "/api/v2/user":
                    return {
                        "id": 9 if token == "child" else 42,
                        "username": "Owner",
                        "restricted": token == "child",
                    }
                if path == "/api/home/users":
                    return {
                        "User": [
                            {
                                "id": 42,
                                "uuid": "owner",
                                "title": "Owner",
                                "protected": True,
                            },
                            {"id": 9, "uuid": "child", "title": "Gregg"},
                        ]
                    }
                if "/switch" in path:
                    return {"authToken": "child" if "/child/" in path else "master"}
                raise AssertionError(path)

            with patch.object(app, "OWNER", local), patch.object(
                app, "PLEX_OWNER_LOGIN", plex_owner.PlexOwnerLogin()
            ), patch.object(
                app, "plex_owner_request", side_effect=request
            ), patch.object(
                app,
                "plex_account",
                side_effect=lambda state, path, **kwargs: request(
                    "client", path, **kwargs
                ),
            ):
                server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()

                def send(path, body=None, cookie="", origin="http://127.0.0.1:8765"):
                    headers = {
                        "Host": "127.0.0.1:8765",
                        "Origin": origin,
                        "Cookie": cookie,
                        "X-Listweavarr-Token": app.SESSION,
                    }
                    if body is not None:
                        headers["Content-Type"] = "application/json"
                    return urllib.request.urlopen(
                        urllib.request.Request(
                            f"http://127.0.0.1:{server.server_port}" + path,
                            data=(
                                json.dumps(body).encode() if body is not None else None
                            ),
                            headers=headers,
                        )
                    )

                try:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        send("/api/owner/plex-enable", {"account_id": "99"})
                    self.assertEqual(error.exception.code, 400)
                    error.exception.close()
                    self.assertFalse((Path(folder) / "owner-plex-id").exists())
                    with send(
                        "/api/owner/plex-enable", {"account_id": "42"}
                    ) as response:
                        setup_cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                    self.assertTrue(app.OWNER.enabled)
                    self.assertTrue(
                        owner_access.OwnerAccess(Path(folder)).enabled,
                        "UI configuration survives restart",
                    )
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        send("/api/state")
                    self.assertEqual(error.exception.code, 401)
                    error.exception.close()
                    with send("/api/state", cookie=setup_cookie) as response:
                        self.assertEqual(
                            json.load(response)["lists"][0]["name"], "Owner list"
                        )
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        send("/api/auth/plex/start", {}, origin="https://wrong.example")
                    self.assertEqual(error.exception.code, 403)
                    error.exception.close()
                    with send("/api/auth/plex/start", {}) as response:
                        pending_cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                    with send("/api/auth/plex/check", {}, pending_cookie) as response:
                        data = json.load(response)
                        self.assertEqual(len(data["profiles"]), 2)
                        self.assertIsNone(response.headers.get("Set-Cookie"))
                        self.assertNotIn("master", json.dumps(data))
                    other_owner_cookie = owner_access.cookie_header(
                        app.OWNER.issue()
                    ).split(";", 1)[0]
                    with send(
                        "/api/auth/profiles/select",
                        {"profile_id": "9", "pin": ""},
                        pending_cookie + "; " + setup_cookie,
                    ) as response:
                        member_cookie = response.headers.get_all("Set-Cookie")[0].split(
                            ";", 1
                        )[0]
                    with send("/api/state", cookie=member_cookie) as response:
                        data = json.load(response)
                        self.assertEqual(data["lists"], [])
                        self.assertEqual(data["active_profile"]["name"], "Gregg")
                    with send("/api/state", cookie=other_owner_cookie) as response:
                        self.assertEqual(len(json.load(response)["lists"]), 1)
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        send("/api/state", cookie=setup_cookie)
                    self.assertEqual(error.exception.code, 401)
                    error.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        send(
                            "/api/auth/profiles/select",
                            {"profile_id": "42", "pin": ""},
                            pending_cookie,
                        )
                    self.assertEqual(error.exception.code, 400)
                    error.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
