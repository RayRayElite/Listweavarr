import datetime
import unittest
from unittest.mock import patch

import app
import trakt_features as features


class TraktFeaturesTests(unittest.TestCase):
    def test_list_search_preserves_owner_and_pagination(self):
        record = {'list': {'name': 'Mixed chronology', 'ids': {'slug': 'mixed'},
                          'user': {'username': 'Owner', 'ids': {'slug': 'owner'}}, 'item_count': 3}}
        with patch.object(features, 'cached_get', return_value={'data': [record], 'headers': {'x-pagination-page-count': '2'}}) as get:
            result = features.search_lists({}, 'Marvel')
        self.assertTrue(result['has_more'])
        self.assertEqual(result['lists'][0]['url'], 'https://trakt.tv/users/owner/lists/mixed')
        self.assertIn('/search/list?', get.call_args.args[0])

    def test_search_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            features.search_lists({}, mode='private')

    def test_title_list_pagination_uses_parent_and_end_header(self):
        response = {'data': [{'name': 'More lists', 'ids': {'trakt': 123}}],
                    'headers': {'x-pagination-page-count': '2'}}
        with patch.object(features, 'resolve_title', return_value={'ids': {'trakt': 42}}), patch.object(features, 'cached_get', return_value=response) as get:
            result = features.title_lists({}, {'type': 'episode', 'tmdb': '1', 'page': 2})
        self.assertEqual(get.call_args.args[0], '/shows/42/lists/personal/popular?page=2&limit=5')
        self.assertEqual(result['page'], 2)
        self.assertFalse(result['has_more'])
        self.assertEqual(result['lists'][0]['url'], 'https://trakt.tv/lists/123')

    def test_title_list_invalid_page_never_requests_network(self):
        with patch.object(features, 'resolve_title') as resolve:
            with self.assertRaises(ValueError):
                features.title_lists({}, {'tmdb': '1', 'page': 0})
        resolve.assert_not_called()

    def test_episode_rating_is_exact_but_lists_are_for_parent(self):
        paths = []
        def get(path, *args):
            paths.append(path)
            return {'data': {'rating': 8, 'votes': 20} if path.endswith('/ratings') else []}
        with patch.object(features, 'resolve_title', return_value={'ids': {'trakt': 42}}), patch.object(features, 'cached_get', side_effect=get):
            result = features.title_features({}, {'type': 'episode', 'tmdb': '1', 'season': 2, 'episode': 3})
        self.assertIn('/shows/42/seasons/2/episodes/3/ratings', paths)
        self.assertIn('/shows/42/lists/personal/popular?page=1&limit=5', paths)
        self.assertEqual(result['scope'], 'parent show')

    def test_source_edit_detected_even_when_count_unchanged(self):
        with patch('providers.trakt_get', return_value=({'updated_at': 'new', 'item_count': 1}, {})):
            result = features.check_source({'source': 'https://trakt.tv/lists/1', 'items': [{}], 'source_version': 'old'}, {})
        self.assertTrue(result['changed'])

    def test_source_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            features.source_base('https://letterboxd.com/users/me/lists/test')

    def test_watch_progress_uses_watched_history_and_source_order(self):
        items = [{'id': 'a', 'title': 'First', 'type': 'movie', 'tmdb': '1'},
                 {'id': 'b', 'title': 'Next', 'type': 'movie', 'tmdb': '2'}]
        catalog = [{'key': '1', 'type': 'movie', 'title': 'First', 'ids': {'tmdb': ['1']}, 'watched': True},
                   {'key': '2', 'type': 'movie', 'title': 'Next', 'ids': {'tmdb': ['2']}, 'watched': False}]
        with patch.object(app, 'plex_catalog', return_value=catalog), patch.object(app, 'match_item', side_effect=lambda i,c: ([c[0 if i['id']=='a' else 1]], 'provider ID')):
            result = app.watch_progress({'items': items}, {'plex': {'url': 'server'}})
        self.assertEqual(result['completed'], 1)
        self.assertEqual(result['next']['id'], 'b')
        self.assertEqual(result['next_available']['id'], 'b')

    def test_watch_progress_never_treats_title_match_as_confirmed(self):
        with patch.object(app, 'plex_catalog', return_value=[]), patch.object(app, 'match_item', return_value=([{'watched': True}], 'title/year')):
            result = app.watch_progress({'items': [{'id': 'a', 'title': 'Film', 'type': 'movie'}]}, {'plex': {'url': 'server'}})
        self.assertEqual(result['items'][0]['state'], 'unknown')
        self.assertEqual(result['completed'], 0)

    def test_calendar_filters_to_followed_titles_and_deduplicates(self):
        date = (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1)).isoformat()
        records = [{'first_aired': date, 'show': {'title': 'Show', 'ids': {'tmdb': 5, 'trakt': 6}},
                    'episode': {'title': 'Episode', 'season': 1, 'number': 2, 'ids': {'trakt': 7, 'tmdb': 8}}}]
        lists = [{'followed': True, 'items': [{'type': 'show', 'tmdb': '5'}]},
                 {'followed': False, 'items': [{'type': 'movie', 'tmdb': '100'}]}]
        with patch.object(features, 'cached_get', return_value={'data': records+records}) as get:
            result = features.calendar({}, lists)
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['show_tmdb'], '5')
        self.assertIn('/shows/', get.call_args.args[0])
        self.assertEqual(result['items'][0]['show_title'],'Show')
        with patch.object(features,'cached_get',return_value={'data':records}),patch('providers.peek_tmdb',return_value={'poster_path':'/show.jpg'}):
            illustrated=features.calendar({},lists)
        self.assertTrue(illustrated['items'][0]['poster'].endswith('/show.jpg'))


if __name__ == '__main__':
    unittest.main()
