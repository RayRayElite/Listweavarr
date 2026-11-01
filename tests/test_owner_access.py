# SPDX-License-Identifier: AGPL-3.0-only
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import app
import owner_access

PASSWORD = "a fixture owner passphrase"


class OwnerAccessTests(unittest.TestCase):
    def fixture(self, folder):
        password_file = Path(folder) / "password.txt"
        password_file.write_text(PASSWORD, encoding="utf-8")
        return (
            owner_access.OwnerAccess(Path(folder) / "private", password_file),
            password_file,
        )

    def test_disabled_mode_preserves_local_use(self):
        with patch.dict("os.environ", {}, clear=True):
            owner = owner_access.OwnerAccess("unused")
        self.assertFalse(owner.enabled)
        self.assertTrue(owner.authorized(None))

    def test_sessions_are_hashed_persistent_revocable_and_bound_to_password(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, password_file = self.fixture(folder)
            token = owner.login(PASSWORD, "fixture-client")
            cookie = owner_access.cookie_header(token)
            self.assertTrue(owner.authorized(cookie))
            store = (Path(folder) / "private" / "owner-sessions.json").read_text()
            self.assertNotIn(token, store)
            self.assertNotIn(PASSWORD, store)
            reopened = owner_access.OwnerAccess(Path(folder) / "private", password_file)
            self.assertTrue(reopened.authorized(cookie))
            reopened.logout(cookie)
            self.assertFalse(
                owner_access.OwnerAccess(
                    Path(folder) / "private", password_file
                ).authorized(cookie)
            )
            new_token = reopened.login(PASSWORD, "fixture-client")
            password_file.write_text("a changed fixture passphrase", encoding="utf-8")
            changed = owner_access.OwnerAccess(Path(folder) / "private", password_file)
            self.assertFalse(changed.authorized(owner_access.cookie_header(new_token)))
            with self.assertRaises(owner_access.LoginError):
                changed.login(PASSWORD, "fixture-client")

    def test_expiry_rate_limit_and_cookie_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, _ = self.fixture(folder)
            token = owner.login(PASSWORD, "good")
            expiry = max(owner.sessions.values())
            with patch("owner_access.time.time", return_value=expiry + 1):
                self.assertFalse(owner.authorized(owner_access.cookie_header(token)))
            for _ in range(5):
                with self.assertRaises(owner_access.LoginError) as caught:
                    owner.login("wrong", "bad")
                self.assertEqual(caught.exception.status, 401)
            with self.assertRaises(owner_access.LoginError) as caught:
                owner.login(PASSWORD, "bad")
            self.assertEqual(caught.exception.status, 429)
            self.assertIn("HttpOnly", owner_access.cookie_header(token, True))
            self.assertIn("SameSite=Strict", owner_access.cookie_header(token, True))
            self.assertIn("Secure", owner_access.cookie_header(token, True))
            self.assertIn("Max-Age=0", owner_access.cookie_header())

    def test_http_auth_gate_login_logout_and_scoped_companion_access(self):
        with tempfile.TemporaryDirectory() as folder:
            owner, _ = self.fixture(folder)
            with patch.object(app, "OWNER", owner):
                server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                base = f"http://127.0.0.1:{server.server_port}"

                def read(path, body=None, cookie=None, **extra):
                    headers = {"Host": "127.0.0.1:8765", **extra}
                    if cookie:
                        headers["Cookie"] = cookie
                    if body is not None:
                        headers["Content-Type"] = "application/json"
                    return urllib.request.urlopen(
                        urllib.request.Request(
                            base + path,
                            data=(
                                json.dumps(body).encode() if body is not None else None
                            ),
                            headers=headers,
                        )
                    )

                try:
                    with read("/") as response:
                        self.assertIn(b"Owner password", response.read())
                        self.assertIn(
                            "frame-ancestors",
                            response.headers["Content-Security-Policy"],
                        )
                    for path, body in (
                        ("/api/state", None),
                        ("/api/session", None),
                        ("/api/request", {}),
                    ):
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            read(path, body)
                        self.assertEqual(caught.exception.code, 401)
                        caught.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        read(
                            "/api/auth/login",
                            {"password": PASSWORD},
                            Origin="https://evil.example",
                        )
                    self.assertEqual(caught.exception.code, 403)
                    caught.exception.close()
                    with read("/api/auth/login", {"password": PASSWORD}) as response:
                        cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                    with read("/api/session", cookie=cookie) as response:
                        self.assertEqual(json.load(response)["csrf"], app.SESSION)
                    with read("/healthz") as response:
                        self.assertEqual(response.status, 200)
                    with patch("app.read_state", return_value={}), patch(
                        "playlist_artwork.authorize", return_value=True
                    ), patch("playlist_artwork.catalogue", return_value={"items": []}):
                        with read(
                            "/api/playlist-companion/artwork",
                            Authorization="Bearer scoped-fixture",
                        ) as response:
                            self.assertEqual(response.status, 200)
                    with read(
                        "/api/auth/logout",
                        {},
                        cookie,
                        **{"X-Listweavarr-Token": app.SESSION},
                    ) as response:
                        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        read("/api/session", cookie=cookie)
                    self.assertEqual(caught.exception.code, 401)
                    caught.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
