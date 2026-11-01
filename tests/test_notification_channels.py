# SPDX-License-Identifier: AGPL-3.0-only
import copy
import io
import json
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, Mock, patch
import notification_channels as channels
import discord_notify
import request_ledger
import backups
import app


class NotificationChannelTests(unittest.TestCase):
    def configure(self, state, kind="ntfy", **extra):
        urls = {
            "ntfy": "https://ntfy.example/private-topic",
            "gotify": "http://127.0.0.1:8000/message",
            "webhook": "https://hooks.example/incoming",
        }
        return channels.configure(
            state,
            {
                "kind": kind,
                "url": urls[kind],
                "token": "private-token",
                "enabled": True,
                "events": ["available"],
                **extra,
            },
        )

    def event(self, state, title="Film"):
        request_ledger.record(
            state,
            {
                "type": "movie",
                "title": title,
                "tmdb": str(len(state.get("requests", [])) + 1),
            },
            status="available",
        )

    def test_opt_in_and_public_data_never_reveal_endpoint_or_token(self):
        state = {}
        self.event(state)
        channels.collect(state)
        self.assertIsNone(channels.next_job(state))
        self.configure(state)
        self.assertNotIn("private-token", json.dumps(channels.public(state)))
        self.assertNotIn("private-topic", json.dumps(channels.public(state)))
        self.assertNotIn("private-token", json.dumps(backups.export(state)))
        channels.collect(state)
        self.assertEqual(
            state["notification_outboxes"]["ntfy"],
            [],
            "Do not replay events from before enabling",
        )

    def test_isolated_queues_dedup_batching_quiet_hours_and_delivery(self):
        state = {}
        self.configure(state, batch=True, quiet_start="22:00", quiet_end="07:00")
        self.configure(state, "gotify")
        self.event(state, "First")
        self.event(state, "Second")
        channels.collect(state)
        channels.collect(state)
        self.assertEqual(len(state["notification_outboxes"]["ntfy"]), 2)
        cfg = state["notification_channels"]["ntfy"]
        self.assertTrue(channels.quiet_now(cfg, time.strptime("23:00", "%H:%M")))
        self.assertFalse(channels.quiet_now(cfg, time.strptime("12:00", "%H:%M")))
        with patch(
            "notification_channels.quiet_now",
            side_effect=lambda cfg: bool(cfg.get("quiet_start")),
        ):
            work = channels.next_job(state)
        self.assertEqual(work["kind"], "gotify")
        with patch("notification_channels.quiet_now", return_value=False):
            work = channels.next_job(state)
        self.assertEqual(len(work["jobs"]), 2)
        self.assertIn("First", work["job"]["content"])
        channels.finish(state, work)
        self.assertTrue(
            all(r["status"] == "sent" for r in state["notification_outboxes"]["ntfy"])
        )
        self.assertTrue(
            all(
                r["status"] == "pending"
                for r in state["notification_outboxes"]["gotify"]
            )
        )

    def test_changed_destination_cancels_pending_and_cannot_finish_new_config(self):
        state = {}
        self.configure(state)
        self.event(state)
        channels.collect(state)
        work = channels.next_job(state)
        self.configure(state, url="https://ntfy.example/new-topic")
        channels.finish(state, work, discord_notify.DeliveryError("old failure"))
        self.assertNotIn("last_error", state["notification_channels"]["ntfy"])
        self.assertEqual(
            state["notification_outboxes"]["ntfy"][0]["status"], "cancelled"
        )

    def test_transport_payloads_and_redirect_or_rate_limit_handling(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        opener = Mock()
        opener.open.return_value = response
        for kind in channels.KINDS:
            cfg = {
                "url": "https://notify.example/"
                + ("message" if kind == "gotify" else "topic"),
                "token": "private-token",
            }
            with patch("urllib.request.build_opener", return_value=opener):
                channels.send(kind, cfg, "Film ready", "available")
            request = opener.open.call_args.args[0]
            self.assertEqual(request.method, "POST")
            if kind == "ntfy":
                self.assertEqual(request.data, b"Film ready")
            else:
                self.assertEqual(json.loads(request.data)["message"], "Film ready")
            header = "X-gotify-key" if kind == "gotify" else "Authorization"
            self.assertIn("private-token", request.headers[header])
        error = urllib.error.HTTPError(
            "https://notify.example/private",
            429,
            "limited",
            {"Retry-After": "120"},
            io.BytesIO(b"private-token"),
        )
        opener.open.side_effect = error
        with patch(
            "urllib.request.build_opener", return_value=opener
        ), self.assertRaises(discord_notify.DeliveryError) as caught:
            channels.send("ntfy", {"url": "https://notify.example/topic"}, "Test")
        self.assertEqual(caught.exception.retry_after, 120)
        self.assertNotIn("private-token", str(caught.exception))
        self.assertIsNone(
            discord_notify.NoRedirect().redirect_request(
                None, None, None, None, None, None
            )
        )

    def test_invalid_configuration_does_not_overwrite_saved_settings(self):
        state = {}
        self.configure(state)
        original = copy.deepcopy(state)
        for extra in (
            {"url": "http://public.example/topic"},
            {"url": "https://user:pass@example/topic"},
            {"url": "https://example/topic?token=secret"},
            {"token": "bad\nheader"},
            {"quiet_start": "23:00", "quiet_end": ""},
            {"quiet_start": "23:00", "quiet_end": "23:00"},
        ):
            with self.assertRaises(ValueError):
                self.configure(state, **extra)
            self.assertEqual(state, original)
        restored = backups.restore(state, {"lists": []}, "merge")
        self.assertEqual(
            restored["notification_channels"]["ntfy"]["token"], "private-token"
        )
        self.assertEqual(restored["notification_channels"]["ntfy"]["collected"], {})
