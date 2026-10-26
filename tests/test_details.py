import unittest
from unittest.mock import patch

import providers


class TitleDetailsTests(unittest.TestCase):
    settings = {'tmdb': {'key': 'private-token'}}

    def test_movie_summary_rating_cast_and_official_trailer(self):
        data = {'title': 'Example', 'overview': 'A synopsis.', 'vote_average': 7.25, 'vote_count': 100, 'poster_path': '/poster.jpg', 'backdrop_path': '/backdrop.jpg', 'runtime': 120, 'release_date': '2020-01-01', 'genres': [{'name': 'Adventure'}], 'credits': {'cast': [{'name': 'Actor', 'character': 'Hero'}], 'crew': [{'name': 'Director', 'job': 'Director'}]}, 'videos': {'results': [{'type': 'Trailer', 'site': 'YouTube', 'key': 'unofficial01', 'official': False}, {'type': 'Trailer', 'site': 'YouTube', 'key': 'official123', 'official': True}]}}
        with patch('providers.cached_tmdb', return_value=data) as lookup:
            result = providers.title_details({'type': 'movie', 'title': 'Example', 'tmdb': '123'}, self.settings)
        self.assertEqual(result['overview'], 'A synopsis.')
        self.assertEqual(result['rating'], 7.25)
        self.assertEqual(result['trailer']['url'], 'https://www.youtube.com/watch?v=official123')
        self.assertEqual(result['poster'], 'https://image.tmdb.org/t/p/w342/poster.jpg')
        self.assertEqual(result['directors'], ['Director'])
        self.assertNotIn('private-token', str(result))
        self.assertTrue(lookup.call_args.args[0].startswith('movie/123?'))

    def test_episode_uses_exact_coordinates_and_labels_series_trailer(self):
        parent = {'name': 'Parent show', 'genres': [{'name': 'Drama'}], 'poster_path': '/show.jpg', 'videos': {'results': [{'site': 'YouTube', 'type': 'Trailer', 'key': 'series12345', 'official': True}]}}
        episode = {'name': 'Episode two', 'overview': 'An episode synopsis.', 'vote_count': 0, 'vote_average': 0}
        with patch('providers.cached_tmdb', side_effect=[parent, episode]) as lookup:
            result = providers.title_details({'type': 'episode', 'title': 'Two', 'tmdb': '999', 'show_tmdb': '10', 'season': '1', 'episode': '2'}, self.settings)
        self.assertTrue(lookup.call_args.args[0].startswith('tv/10/season/1/episode/2?'))
        self.assertEqual(result['show_title'], 'Parent show')
        self.assertEqual(result['trailer']['scope'], 'series')
        self.assertIsNone(result['rating'])

    def test_absent_or_invalid_trailer_remains_unavailable(self):
        data = {'title': 'Example', 'videos': {'results': [{'site': 'YouTube', 'type': 'Trailer', 'key': 'javascript:alert(1)'}, {'site': 'Vimeo', 'type': 'Trailer', 'key': '123456789'}]}}
        with patch('providers.cached_tmdb', return_value=data):
            result = providers.title_details({'type': 'movie', 'title': 'Example', 'tmdb': '1'}, self.settings)
        self.assertIsNone(result['trailer'])

    def test_episode_includes_guest_cast_without_duplicates(self):
        actor = {'id': 1, 'name': 'Regular'}
        data = {'name': 'Episode', 'credits': {'cast': [actor]}, 'guest_stars': [actor, {'id': 2, 'name': 'Guest'}]}
        with patch('providers.cached_tmdb', side_effect=[{'name': 'Show'}, data]):
            result = providers.title_details({'type': 'episode', 'title': 'Episode', 'tmdb': '99', 'show_tmdb': '10', 'season': '1', 'episode': '2'}, self.settings)
        self.assertEqual([p['name'] for p in result['cast']], ['Regular', 'Guest'])

    def test_poster_path_cannot_point_at_an_arbitrary_host(self):
        for path in ('https://attacker.test/image.jpg', '//attacker.test/image.jpg', '/../../secret', '/image.jpg?token=secret'):
            self.assertIsNone(providers.image_url(path))

    def test_missing_id_does_not_guess_by_title(self):
        with patch('providers.enrich', side_effect=lambda row, settings: row), patch('providers.cached_tmdb') as lookup, self.assertRaisesRegex(ValueError, 'TMDB or IMDb ID'):
            providers.title_details({'type': 'movie', 'title': 'A common title'}, self.settings)
        lookup.assert_not_called()

    def test_no_token_gives_actionable_message(self):
        with self.assertRaisesRegex(ValueError, 'Connections'):
            providers.title_details({'type': 'movie', 'title': 'Example', 'tmdb': '1'}, {})

    def test_show_uses_all_season_credits_without_truncating_cast(self):
        data = {'name': 'Series', 'credits': {'cast': [{'id': 999, 'name': 'Newest season only'}]},
                'aggregate_credits': {'cast': [{'id': n, 'name': f'Actor {n}', 'profile_path': '/actor.jpg', 'total_episode_count': 100, 'popularity': 12.5, 'roles': [{'character': 'First role'}, {'character': 'Second role'}, {'character': 'First role'}]} for n in range(40)],
                                      'crew': [{'id': 50, 'name': 'Director and producer', 'popularity': 20, 'jobs': [{'job': 'Director', 'episode_count': 10}, {'job': 'Producer', 'episode_count': 100}]}]}}
        with patch('providers.cached_tmdb', return_value=data) as lookup:
            result = providers.title_details({'type': 'show', 'title': 'Series', 'tmdb': '10'}, self.settings)
        self.assertIn('aggregate_credits', lookup.call_args.args[0])
        self.assertEqual(len(result['cast']), 40)
        self.assertEqual(result['cast'][0]['character'], 'First role / Second role')
        self.assertEqual(result['cast'][0]['photo'], 'https://image.tmdb.org/t/p/w342/actor.jpg')
        self.assertEqual(result['director_people'][0]['id'], 50)
        self.assertEqual(result['producer_people'][0]['id'], 50)
        self.assertEqual(result['cast'][0]['episode_count'], 100)
        self.assertEqual(result['cast'][0]['popularity'], 12.5)
        self.assertEqual(result['director_people'][0]['episode_count'], 10)
        self.assertEqual(result['producer_people'][0]['episode_count'], 100)


if __name__ == '__main__':
    unittest.main()
