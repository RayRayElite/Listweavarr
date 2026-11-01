# SPDX-License-Identifier: AGPL-3.0-only
import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import app


class SessionRecoveryTests(unittest.TestCase):
    def test_expired_token_is_identified_before_any_action_and_can_be_renewed(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch(
                "app.read_state",
                side_effect=AssertionError("No state reads before session check"),
            ), patch("app.save_state") as save, patch("app.arr_call") as manager:
                req = urllib.request.Request(
                    base + "/api/request",
                    data=b"{}",
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": "expired",
                    },
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req)
                self.assertEqual(caught.exception.code, 403)
                self.assertEqual(json.load(caught.exception)["code"], "session_expired")
                caught.exception.close()
                req = urllib.request.Request(
                    base + "/api/session", headers={"Host": "127.0.0.1:8765"}
                )
                with urllib.request.urlopen(req) as response:
                    self.assertEqual(json.load(response)["csrf"], app.SESSION)
                save.assert_not_called()
                manager.assert_not_called()
                req = urllib.request.Request(
                    base + "/api/request",
                    data=b"{}",
                    headers={"Host": "evil.example", "X-Listweavarr-Token": "expired"},
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req)
                self.assertNotIn("code", json.load(caught.exception))
                caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()
