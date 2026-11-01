# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import unittest
import activity
import request_ledger


class RequestDiagnosticTests(unittest.TestCase):
    def test_import_reason_is_specific_bounded_and_redacted(self):
        records = [
            {
                "trackedDownloadStatus": "warning",
                "status": "completed",
                "statusMessages": [
                    {
                        "title": "No files found are eligible for import",
                        "messages": [
                            "/downloads/film",
                            "key=private-key https://host/path?token=private-key",
                            "x" * 1000,
                        ],
                    }
                ],
            }
        ]
        original = copy.deepcopy(records)
        result = activity.diagnostic(
            {"state": "import_blocked"},
            records,
            "radarr",
            {"radarr": {"key": "private-key"}},
        )
        self.assertEqual(result["stage"], "import_path")
        self.assertIn("mounts", " ".join(result["next_steps"]))
        self.assertNotIn("private-key", json.dumps(result))
        self.assertNotIn("https://host", json.dumps(result))
        self.assertLessEqual(max(map(len, result["evidence"])), 700)
        self.assertEqual(records, original)

    def test_permissions_and_quality_are_reported_as_evidence_not_auto_fixes(self):
        for message, stage in [
            ("Access denied to library", "permissions"),
            ("Quality does not meet profile", "import_quality"),
        ]:
            result = activity.diagnostic(
                {"state": "import_blocked"}, [{"errorMessage": message}], "sonarr", {}
            )
            self.assertEqual(result["stage"], stage)
            self.assertIn(message, result["evidence"])
        self.assertEqual(
            activity.queue_label(
                [{"status": "completed", "trackedDownloadState": "importBlocked"}]
            )[0],
            "import_blocked",
        )
        self.assertEqual(
            activity.queue_label(
                [{"status": "downloading", "trackedDownloadStatus": "warning"}]
            )[1],
            "Download needs attention",
        )

    def test_ledger_separates_manager_import_and_plex_and_retains_connection_warning(
        self,
    ):
        state = {}
        row = request_ledger.record(
            state, {"type": "movie", "tmdb": "1", "title": "Film"}, status="requested"
        )
        request_ledger.apply_status(
            state, {row["id"]: {"state": "downloaded", "label": "Imported in Radarr"}}
        )
        self.assertEqual(row["status"], "imported")
        self.assertEqual(row["diagnostic"]["stage"], "plex_scan")
        request_ledger.apply_status(
            state, {row["id"]: {"state": "unavailable", "label": "Offline"}}
        )
        self.assertEqual(row["status"], "imported")
        self.assertEqual(row["check_warning"], "Offline")
        request_ledger.apply_status(
            state, {row["id"]: {"state": "available", "label": "In Plex"}}
        )
        self.assertEqual(row["status"], "available")
        self.assertEqual(row["diagnostic"]["stage"], "ready")
        self.assertNotIn("check_warning", row)

    def test_evidence_is_exact_episode_scope(self):
        activity._cache.clear()

        def read(settings, service, path):
            if path == "series":
                return [{"id": 1, "tvdbId": 2}]
            if path.startswith("episode?"):
                return [
                    {
                        "id": 10,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDateUtc": "2020-01-01",
                        "hasFile": False,
                    },
                    {
                        "id": 11,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "airDateUtc": "2020-01-01",
                        "hasFile": False,
                    },
                ]
            return {
                "records": [
                    {
                        "seriesId": 1,
                        "episodeId": 10,
                        "status": "completed",
                        "trackedDownloadStatus": "warning",
                        "errorMessage": "No eligible files",
                    },
                    {
                        "seriesId": 1,
                        "episodeId": 11,
                        "status": "completed",
                        "errorMessage": "Other episode only",
                    },
                ]
            }

        result = activity.summarize(
            [
                {
                    "id": "one",
                    "type": "episode",
                    "show_tvdb": "2",
                    "season": 1,
                    "episode": 1,
                }
            ],
            {"sonarr": {"url": "http://fixture", "key": "fixture"}},
            read,
        )
        diagnostic = result["items"]["one"]["diagnostic"]
        self.assertIn("No eligible files", diagnostic["evidence"])
        self.assertNotIn("Other episode only", diagnostic["evidence"])
        self.assertNotIn("_queue_evidence", result["items"]["one"])
