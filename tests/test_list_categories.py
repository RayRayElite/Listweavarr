# SPDX-License-Identifier: AGPL-3.0-only
import unittest
import copy
import app
import list_categories as categories
import official_lists
import catalogue_feed


class CategoryTests(unittest.TestCase):
    def test_legacy_defaults_match_requested_groups(self):
        for name in [
            "Naruto",
            "DC Animated MOVIE Universe",
            "Alien Vs Predator Universe",
            "Neon Genesis Evangelion",
            "Transformers Stand-Alone",
        ]:
            self.assertEqual(categories.category({"name": name}), "franchises")
        for name in [
            "IMDB Top 250 Movies",
            "TMDB Top 100 Rated TV Shows",
            "The Academy Awards",
            "TIFF's People's Choice Awards",
        ]:
            self.assertEqual(categories.category({"name": name}), "top")
        for name in [
            "Ray Recommends",
            "So Bad Its Good",
            "MindFuck Collection",
            "Christmas Collection",
            "Halloween",
        ]:
            self.assertEqual(categories.category({"name": name}), "curated")
        self.assertEqual(
            categories.category({"name": "Halloween", "category": "franchises"}),
            "franchises",
        )
        for invalid in ("all", "private", {}, None):
            with self.assertRaises(ValueError):
                categories.validate(invalid)

    def test_publish_choice_versions_and_feed_round_trip(self):
        entry = {
            "id": "fixture",
            "name": "A themed selection",
            "items": [app.normalize({"title": "Film", "type": "movie", "tmdb": "1"})],
        }
        original = copy.deepcopy(entry)
        document, working, report = official_lists.prepare_publish(
            entry, {"version": 1, "lists": []}, app.normalize, "curated"
        )
        self.assertEqual(document["lists"][0]["category"], "curated")
        self.assertEqual(working["official_category"], "curated")
        self.assertEqual(entry, original)
        same, _, report = official_lists.prepare_publish(
            working, document, app.normalize, "curated"
        )
        self.assertFalse(report["changed"])
        moved, _, report = official_lists.prepare_publish(
            working, document, app.normalize, "top"
        )
        self.assertTrue(report["changed"])
        self.assertEqual(moved["lists"][0]["version"], 2)
        clean = catalogue_feed.validate(moved, app.normalize)
        self.assertEqual(clean["lists"][0]["category"], "top")
        invalid = copy.deepcopy(moved)
        invalid["lists"][0]["category"] = "invalid"
        with self.assertRaises(ValueError):
            catalogue_feed.validate(invalid, app.normalize)
