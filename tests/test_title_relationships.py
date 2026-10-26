import unittest
from unittest.mock import Mock

import title_relationships as relationships


class RelationshipTests(unittest.TestCase):
    def test_story_sequence_preserves_order_and_highlights_current(self):
        collection = {'name': 'Iron Man Collection', 'parts': [
            {'id': 68721, 'title': 'Iron Man 3'}, {'id': 1726, 'title': 'Iron Man'},
            {'id': 10138, 'title': 'Iron Man 2'}]}
        result = relationships.sections('movie', '10138', {'title': 'Iron Man 2'}, collection, [], {}, Mock(), lambda p: p)
        self.assertEqual([r['tmdb'] for r in result['sequence']['items']], ['1726', '10138', '68721'])
        self.assertEqual([r['current'] for r in result['sequence']['items']], [False, True, False])
        self.assertEqual(result['franchise']['items'], [])

    def test_collection_does_not_imply_sequels(self):
        collection = {'name': 'Franchise', 'parts': [{'id': 1, 'title': 'Current'}, {'id': 2, 'title': 'Spin-off'}]}
        rows = [{'key': 'movie:2', 'group': 'Franchise'}, {'key': 'movie:3', 'group': 'Recommendations'}]
        result = relationships.sections('movie', '1', {'title': 'Current'}, collection, rows, {}, Mock(), lambda p: p)
        self.assertEqual(result['sequence']['items'], [])
        self.assertEqual(result['franchise']['items'][0]['tmdb'], '2')
        self.assertEqual(result['related']['items'][0]['key'], 'movie:3')

    def test_recommendations_do_not_confirm_franchise(self):
        rows = [{'key': 'tv:2', 'group': 'Recommendations'}]
        result = relationships.sections('show', '1', {'name': 'Current'}, None, rows, {}, Mock(), lambda p: p)
        self.assertEqual(result['franchise']['items'], [])
        self.assertEqual(result['related']['items'], rows)
