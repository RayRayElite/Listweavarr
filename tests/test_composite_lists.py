# SPDX-License-Identifier: AGPL-3.0-only
import copy
import unittest
import composite_lists as composite


def movie(identifier, **values):
    return {
        "id": identifier,
        "type": "movie",
        "title": identifier,
        "tmdb": identifier,
        **values,
    }


class CompositeTests(unittest.TestCase):
    def sources(self):
        return [
            {"id": "a", "items": [movie("1"), movie("2"), movie("1")]},
            {"id": "b", "items": [movie("2"), movie("3")]},
            {"id": "c", "items": [movie("3")]},
        ]

    def test_operations_preserve_first_order_and_do_not_mutate(self):
        lists = self.sources()
        before = copy.deepcopy(lists)
        for operation, expected in [
            ("union", ["1", "2", "3"]),
            ("intersection", ["2"]),
            ("difference", ["1"]),
        ]:
            result = composite.preview(
                {"sources": ["a", "b"], "operation": operation}, lists
            )
            self.assertEqual([r["tmdb"] for r in result["items"]], expected)
        self.assertEqual(lists, before)

    def test_exclusion_and_preview_invalidation(self):
        lists = self.sources()
        body = {"sources": ["a", "b"], "exclude": ["c"]}
        first = composite.preview(body, lists)
        self.assertEqual([r["tmdb"] for r in first["items"]], ["1", "2"])
        self.assertEqual(first["provenance"][0], {"source": "a", "entry": "1"})
        lists[1]["items"].append(movie("4"))
        self.assertNotEqual(
            first["fingerprint"], composite.preview(body, lists)["fingerprint"]
        )

    def test_conflicting_ids_scope_and_unknown_identity(self):
        self.assertFalse(
            composite.exact(movie("1", imdb="tt1"), movie("2", imdb="tt1"))
        )
        self.assertFalse(
            composite.exact(
                {"type": "show", "tmdb": "1"},
                {"type": "episode", "show_tmdb": "1", "season": "1", "episode": "1"},
            )
        )
        self.assertFalse(
            composite.exact(
                {"type": "movie", "title": "Same"}, {"type": "movie", "title": "Same"}
            )
        )
        self.assertTrue(
            composite.exact(
                {"type": "episode", "show_tmdb": "1", "season": "01", "episode": "02"},
                {"type": "episode", "show_tmdb": "1", "season": "1", "episode": "2"},
            )
        )

    def test_runtime_data_never_enters_generated_items(self):
        lists = self.sources()
        lists[0]["items"][0].update(
            plex_keys=["private"], request_log={"secret": "private"}
        )
        result = composite.preview({"sources": ["a", "b"]}, lists)
        self.assertNotIn("plex_keys", result["items"][0])
        self.assertNotIn("request_log", result["items"][0])

    def test_invalid_rules_rejected(self):
        for body in [
            {"sources": ["a"]},
            {"sources": ["a", "a"]},
            {"sources": ["a", "gone"]},
            {"sources": ["a", "b"], "exclude": ["a"]},
            {"sources": ["a", "b"], "operation": "unknown"},
        ]:
            with self.assertRaises(ValueError):
                composite.preview(body, self.sources())
