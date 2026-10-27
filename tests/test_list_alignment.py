# SPDX-License-Identifier: AGPL-3.0-only
import unittest
import list_alignment
import text_list_builder


class AlignmentTests(unittest.TestCase):
    def test_primary_order_and_shared_anchors(self):
        result = list_alignment.align([1, 2, 3], [0, 1, 4, 2, 3, 5], lambda row: row)
        self.assertEqual(result["items"], [0, 1, 4, 2, 3, 5])
        self.assertEqual(result["added"], 3)
        self.assertEqual(result["conflicts"], [])

    def test_contradictions_are_not_guessed(self):
        result = list_alignment.align([1, 2], [2, 3, 1], lambda row: row)
        self.assertEqual(result["items"], [1, 2])
        self.assertEqual(result["conflicts"][0]["items"], [3])
        disconnected = list_alignment.align([1, 2], [3, 4], lambda row: row)
        self.assertEqual(len(disconnected["conflicts"]), 1)

    def test_deduplication_and_javascript_sheet_labels(self):
        result = list_alignment.align([1, 1, 2], [1, 3, 3, 2], lambda row: row)
        self.assertEqual(result["items"], [1, 3, 2])
        self.assertEqual(result["primary_duplicates"], [1])
        self.assertEqual(result["secondary_duplicates"], [3])
        tabs = text_list_builder.sheet_tabs(
            r'''items.push({name: "NCIS \x26 JAG\'s guide", pageUrl: "one", gid: "123"'''
        )
        self.assertEqual(tabs, [("NCIS & JAG's guide", "123")])
