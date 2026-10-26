# SPDX-License-Identifier: AGPL-3.0-only
import copy
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
import app
import backups
import discord_notify
import manager_routes
import request_ledger


class WorkflowUnitTests(unittest.TestCase):
    def fixture(self):
        return {
            "settings": {
                "radarr": {"url": "http://primary:7878", "key": "primary-secret"}
            },
            "lists": [],
        }

    def test_routes_keep_credentials_private_and_tiers_distinct(self):
        state = self.fixture()
        route = manager_routes.save(
            state,
            {
                "service": "radarr",
                "name": "UHD",
                "url": "http://uhd:7878",
                "key": "uhd-secret",
                "tier": "4k",
                "default": True,
            },
        )
        self.assertEqual(manager_routes.default(state, "radarr", "4k"), route["id"])
        settings = manager_routes.routed(state, "radarr", route["id"])
        self.assertEqual(settings["radarr"]["key"], "uhd-secret")
        self.assertEqual(settings["_requested_tier"], "4k")
        self.assertEqual(state["settings"]["radarr"]["key"], "primary-secret")
        self.assertNotIn("secret", json.dumps(manager_routes.public(state)))
        self.assertNotIn("secret", json.dumps(backups.export(state)))
        movie = {"type": "movie", "tmdb": "1", "title": "Film"}
        primary = request_ledger.record(state, movie, status="requested")
        uhd = request_ledger.record(
            state, movie, status="requested", route=route["id"], tier="4k"
        )
        self.assertNotEqual(primary["id"], uhd["id"])
        state["release_watchlist"] = [
            dict(movie, manager_monitor={"route": route["id"], "tier": "4k"})
        ]
        before = len(state["requests"])
        request_ledger.record(
            state,
            movie,
            mode="monitor",
            status="monitored",
            route=route["id"],
            tier="4k",
        )
        request_ledger.migrate(state)
        self.assertEqual(len(state["requests"]), before + 1)
        route["enabled"] = False
        with self.assertRaisesRegex(ValueError, "disabled"):
            manager_routes.routed(state, "radarr", route["id"])

    def test_4k_ownership_is_not_satisfied_by_hd(self):
        sections = ET.fromstring(
            '<MediaContainer><Directory key="1" type="movie" title="Movies"/></MediaContainer>'
        )
        hd = ET.fromstring(
            '<MediaContainer totalSize="1"><Video ratingKey="10" title="Film" year="2020"><Guid id="tmdb://1"/><Media videoResolution="1080" width="1920"/></Video></MediaContainer>'
        )
        cfg = {"plex": {"url": "http://plex", "key": "secret"}}
        with patch.object(app, "remote", side_effect=[sections, hd]):
            self.assertEqual(len(app.plex_catalog(cfg)), 1)
        with patch.object(app, "remote", side_effect=[sections, hd]):
            self.assertEqual(app.plex_catalog(dict(cfg, _requested_tier="4k")), [])
        movie = hd.find("Video")
        movie.find("Media").set("videoResolution", "4k")
        movie.find("Media").set("width", "3840")
        self.assertTrue(app.has_4k(movie))
        leaves = ET.fromstring(
            '<MediaContainer totalSize="2"><Video ratingKey="1" parentIndex="1" index="1"><Media videoResolution="1080"/></Video><Video ratingKey="2" parentIndex="1" index="2"><Media videoResolution="4k"/></Video></MediaContainer>'
        )
        with patch.object(app, "remote", return_value=leaves):
            self.assertEqual(
                [
                    r["episode"]
                    for r in app.plex_leaves(dict(cfg, _requested_tier="4k"), "3")
                ],
                ["2"],
            )

    def test_discord_validates_destinations_and_disables_mentions(self):
        url = "https://discord.com/api/webhooks/123/test_token"
        for invalid in (
            "http://discord.com/api/webhooks/123/token",
            "https://discord.com.evil/api/webhooks/123/token",
            "https://user:pass@discord.com/api/webhooks/123/token",
            "https://discord.com/api/webhooks/123/token?redirect=evil",
        ):
            with self.assertRaises(ValueError):
                discord_notify.validate_url(invalid)
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        opener = unittest.mock.Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            discord_notify.send(url, "@everyone Film ready")
        sent = opener.open.call_args.args[0]
        self.assertEqual(json.loads(sent.data)["allowed_mentions"], {"parse": []})
        self.assertEqual(sent.method, "POST")
        self.assertIsNone(
            discord_notify.NoRedirect().redirect_request(
                None, None, None, None, None, None
            )
        )

    def test_discord_outbox_idempotence_and_rate_limits(self):
        state = self.fixture()
        url = "https://discord.com/api/webhooks/123/test_token"
        with patch("discord_notify.time.time", return_value=100):
            discord_notify.configure(
                state, {"url": url, "enabled": True, "events": ["available"]}
            )
        state["requests"] = [
            {
                "id": "movie",
                "item": {"type": "movie", "title": "Film"},
                "events": [
                    {"at": 99, "status": "available"},
                    {"at": 101, "status": "available"},
                ],
            }
        ]
        discord_notify.collect(state)
        discord_notify.collect(state)
        self.assertEqual(len(state["notification_outbox"]), 1)
        job = state["notification_outbox"][0]
        with patch("discord_notify.time.time", return_value=105):
            discord_notify.finish(
                state,
                job["id"],
                discord_notify.DeliveryError("Rate limited", retry_after=120),
            )
        self.assertEqual(job["status"], "pending")
        self.assertGreaterEqual(job["next_at"], 225)
        discord_notify.finish(state, job["id"])
        discord_notify.collect(state)
        self.assertEqual(len(state["notification_outbox"]), 1)
        self.assertEqual(job["status"], "sent")
        self.assertNotIn("test_token", json.dumps(discord_notify.public(state)))
        self.assertNotIn("test_token", json.dumps(backups.export(state)))
        discord_notify.configure(state, {"enabled": False, "events": ["available"]})
        self.assertIsNone(discord_notify.next_job(state))
        error = urllib.error.HTTPError(
            url, 429, "Rate limited", {"Retry-After": "125"}, io.BytesIO(b"{}")
        )
        opener = unittest.mock.Mock()
        opener.open.side_effect = error
        with (
            patch("urllib.request.build_opener", return_value=opener),
            self.assertRaises(discord_notify.DeliveryError) as caught,
        ):
            discord_notify.send(url, "Test")
        self.assertEqual(caught.exception.retry_after, 125)
        self.assertNotIn("test_token", str(caught.exception))


class WorkflowApiTests(unittest.TestCase):
    def test_queue_approve_route_and_decline_without_unapproved_writes(self):
        state = {
            "settings": {"radarr": {"url": "http://primary", "key": "primary-secret"}},
            "request_policy": {"require_approval": True},
            "lists": [
                {
                    "id": "list",
                    "name": "List",
                    "items": [
                        {
                            "id": "movie",
                            "type": "movie",
                            "title": "Film",
                            "tmdb": "1",
                            "status": "missing",
                        }
                    ],
                }
            ],
        }
        with (
            tempfile.TemporaryDirectory(dir=app.ROOT) as folder,
            patch.object(app, "DATA", Path(folder)),
        ):
            route = manager_routes.save(
                state,
                {
                    "name": "4K",
                    "service": "radarr",
                    "tier": "4k",
                    "url": "http://uhd",
                    "key": "uhd-secret",
                },
            )
            app.save_state(state)
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def post(path, body):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/" + path,
                    data=json.dumps(body).encode(),
                    headers={
                        "Host": "127.0.0.1:8765",
                        "X-Listweavarr-Token": app.SESSION,
                    },
                )
                with urllib.request.urlopen(req) as response:
                    return json.load(response)

            def rejected(path, body):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    post(path, body)
                failure.exception.close()

            try:
                with patch.object(
                    app, "request_item", return_value="Search submitted"
                ) as send:
                    post(
                        "request",
                        {
                            "list_id": "list",
                            "ids": ["movie"],
                            "options": {"radarr": {"profile": "1", "root": "/media"}},
                        },
                    )
                    send.assert_not_called()
                    queued = post("requests/list", {})["items"][0]
                    self.assertEqual(queued["status"], "awaiting_approval")
                    rejected(
                        "requests/retry",
                        {
                            "id": queued["id"],
                            "confirmed": True,
                            "profile": "1",
                            "root": "/media",
                        },
                    )
                    send.assert_not_called()
                    post(
                        "requests/retry",
                        {
                            "id": queued["id"],
                            "confirmed": True,
                            "approved": True,
                            "profile": "1",
                            "root": "/media",
                        },
                    )
                    send.assert_called_once()
                    self.assertEqual(
                        send.call_args.args[1]["radarr"]["key"], "primary-secret"
                    )
                with patch(
                    "providers.list_details",
                    return_value={"title": "Film", "release_date": "2020-01-01"},
                ):
                    created = post(
                        "requests/create",
                        {
                            "item": {"type": "movie", "tmdb": "1"},
                            "tier": "4k",
                            "route": route["id"],
                        },
                    )
                uhd = next(
                    r for r in created["items"] if r["id"] == created["request_id"]
                )
                self.assertEqual(uhd["tier"], "4k")
                self.assertNotEqual(uhd["id"], queued["id"])
                rejected("requests/decline", {"id": uhd["id"], "expected_updated": 0})
                result = post(
                    "requests/decline",
                    {
                        "id": uhd["id"],
                        "expected_updated": uhd["updated_at"],
                        "reason": "Later",
                    },
                )
                self.assertEqual(
                    next(r for r in result["items"] if r["id"] == uhd["id"])["status"],
                    "declined",
                )
                with patch.object(app, "request_item") as send:
                    rejected(
                        "requests/retry",
                        {
                            "id": uhd["id"],
                            "confirmed": True,
                            "approved": True,
                            "profile": "1",
                            "root": "/uhd",
                        },
                    )
                    send.assert_not_called()
                with patch(
                    "providers.list_details",
                    return_value={"title": "Film", "release_date": "2020-01-01"},
                ):
                    reopened = post(
                        "requests/create",
                        {
                            "item": {"type": "movie", "tmdb": "1"},
                            "tier": "4k",
                            "route": route["id"],
                        },
                    )
                with patch.object(
                    app, "request_item", return_value="Sent to UHD"
                ) as send:
                    post(
                        "requests/retry",
                        {
                            "id": reopened["request_id"],
                            "confirmed": True,
                            "approved": True,
                            "profile": "2",
                            "root": "/uhd",
                        },
                    )
                    self.assertEqual(
                        send.call_args.args[1]["radarr"]["key"], "uhd-secret"
                    )
                    self.assertEqual(send.call_args.args[1]["_requested_tier"], "4k")
                with patch("discord_notify.send") as send:
                    rejected("notifications/test", {})
                    send.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
