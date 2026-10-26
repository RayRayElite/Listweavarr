import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import app
import providers


def imdb_page(items, total, next_page=''):
    data = {'@type': 'ItemList', 'name': 'Mixed chronology', 'numberOfItems': total,
            'itemListElement': [{'position': n, 'item': {'@type': kind, 'name': title, 'url': 'https://www.imdb.com/title/' + identifier + '/'}} for n, kind, title, identifier in items]}
    return '<script type="application/ld+json">' + json.dumps(data) + '</script>' + (f'<a rel="next" href="{next_page}">Next</a>' if next_page else '')


class MixedProviderTests(unittest.TestCase):
    def test_imdb_mixed_pages_preserve_scope_order_and_duplicate_titles(self):
        pages = [imdb_page([(1, 'Movie', 'Film', 'tt1'), (2, 'TVEpisode', 'Pilot', 'tt2')], 4, '?page=2'),
                 imdb_page([(3, 'TVSeries', 'Series', 'tt3'), (4, 'Movie', 'Film again', 'tt1')], 4)]
        with patch('providers.fetch', side_effect=pages):
            result = providers.imdb('https://www.imdb.com/list/ls123/', lambda *a: None)
        self.assertEqual([r['type'] for r in result['items']], ['movie', 'episode', 'show', 'movie'])
        self.assertTrue(result['items'][1]['metadata_unresolved'])
        self.assertNotEqual(result['items'][0]['source_key'], result['items'][3]['source_key'])

    def test_imdb_truncated_list_is_never_accepted(self):
        with patch('providers.fetch', return_value=imdb_page([(1, 'Movie', 'Film', 'tt1')], 2)):
            with self.assertRaisesRegex(ValueError, 'complete ordered list'):
                providers.imdb('https://www.imdb.com/list/ls123/', lambda *a: None)

    def test_imdb_repeated_next_page_is_rejected(self):
        with patch('providers.fetch', return_value=imdb_page([(1, 'Movie', 'Film', 'tt1')], 2, '/list/ls123/')):
            with self.assertRaisesRegex(ValueError, 'pagination repeated'):
                providers.imdb('https://www.imdb.com/list/ls123/', lambda *a: None)

    def test_csv_position_order_and_unresolved_episode_survive_lookup_failure(self):
        csv = 'Position,Const,Title,Title Type,Year\n3,tt3,Series,TV Series,2020\n2,tt2,Pilot,TV Episode,2020\n1,tt1,Film,Movie,2019'
        with patch('providers.enrich', side_effect=ValueError('No metadata available')):
            rows = app.import_items(csv, 'csv', {'tmdb': {'key': 'test'}})
        self.assertEqual([r['imdb'] for r in rows], ['tt1', 'tt2', 'tt3'])
        self.assertEqual([r['type'] for r in rows], ['movie', 'episode', 'show'])
        self.assertTrue(rows[1]['metadata_unresolved'])
        self.assertIn('metadata_note', rows[1])

    def test_season_resolution_does_not_expand_to_whole_show(self):
        with patch('providers.tmdb', side_effect=[{'tv_results': [{'id': 10}]}, {'tvdb_id': 20}]):
            result = providers.enrich({'type': 'season', 'title': 'Season 2', 'season': '2', 'imdb': 'tt1'}, {'tmdb': {'key': 'test'}})
        self.assertEqual(result['type'], 'season')
        self.assertEqual(result['show_tmdb'], '10')
        self.assertEqual(result['season'], '2')

    def test_episode_given_series_id_is_not_expanded_to_whole_show(self):
        with patch('providers.tmdb', return_value={'tv_results': [{'id': 10}]}):
            with self.assertRaisesRegex(ValueError, 'not an episode ID'):
                providers.enrich({'type': 'episode', 'title': 'Pilot', 'imdb': 'tt1', 'metadata_unresolved': True}, {'tmdb': {'key': 'test'}})

    def chrono_page(self):
        timelines = [{'id': 'main', 'name': 'Main continuity', 'events': [
            {'id': 'episode-block', 'title': 'Series story block', 'watchOrder': 2, 'media': {'type': 'show', 'title': 'Parent', 'releaseDate': '2020'}},
            {'id': 'film', 'title': 'Film', 'watchOrder': 1, 'media': {'type': 'film', 'releaseDate': '2019'}}]},
            {'id': 'alternate', 'name': 'Alternate', 'events': [{'id': 'alternate-film', 'title': 'Other', 'watchOrder': 3, 'media': {'type': 'film'}}]}]
        record = 'a:' + json.dumps(['$', '$L1', None, {'timelines': timelines}]) + '\n'
        # Flight chunks can split in the middle of a JSON record.
        return ''.join('<script>self.__next_f.push(' + json.dumps([1, part]) + ')</script>' for part in [record[:60], record[60:]])

    def test_chronocanon_all_timelines_and_block_scope_are_preserved(self):
        with patch('providers.fetch', return_value=self.chrono_page()):
            result = providers.chronocanon('https://chronocanon.com/franchise/example', lambda *a: None)
        self.assertEqual([r['title'] for r in result['items']], ['Film', 'Series story block', 'Other'])
        self.assertEqual(result['items'][1]['type'], 'season')
        self.assertTrue(result['items'][1]['metadata_unresolved'])
        self.assertNotIn('show_tmdb', result['items'][1])
        self.assertIn('timeline=all', result['source'])

    def test_chronocanon_selects_one_continuity(self):
        with patch('providers.fetch', return_value=self.chrono_page()):
            result = providers.chronocanon('https://chronocanon.com/franchise/example?timeline=alternate', lambda *a: None)
        self.assertEqual([r['title'] for r in result['items']], ['Other'])

    def test_chronocanon_rejects_unknown_continuity(self):
        with patch('providers.fetch', return_value=self.chrono_page()):
            with self.assertRaisesRegex(ValueError, 'Unknown timeline'):
                providers.chronocanon('https://chronocanon.com/franchise/example?timeline=missing', lambda *a: None)


class RefreshAndPlaylistTests(unittest.TestCase):
    def test_comparison_reports_availability_and_marks_playlist_outdated(self):
        import threading
        import urllib.request
        with tempfile.TemporaryDirectory() as folder, patch('app.DATA', Path(folder)):
            entry = {'id': 'list', 'name': 'Mixed', 'items': [{'id': 'm', 'type': 'movie', 'title': 'Film', 'status': 'unchecked'}], 'comparison_baseline': {'m': 'missing'}, 'playlist': {'fingerprint': 'old'}}
            app.save_state({'settings': {}, 'lists': [entry]})
            server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/compare', data=json.dumps({'list_id': 'list'}).encode(), headers={'Host': '127.0.0.1:8765', 'X-ReelCheck-Token': app.SESSION})
            try:
                with patch('app.compare', return_value=[{'id': 'm', 'type': 'movie', 'title': 'Film', 'status': 'available', 'plex_keys': ['1']}]), patch('app.remote') as remote:
                    with urllib.request.urlopen(request) as response:
                        result = json.load(response)
                    remote.assert_not_called()
                self.assertEqual(result['availability_report'], [{'title': 'Film', 'from': 'missing', 'to': 'available'}])
                self.assertTrue(result['playlist_needs_update'])
                self.assertNotIn('comparison_baseline', app.read_state()['lists'][0])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_refresh_report_distinguishes_reorder_from_add_remove(self):
        before = [{'id': 'a', 'title': 'Film', 'type': 'movie'}, {'id': 'b', 'title': 'Pilot', 'type': 'episode', 'episode': '1'}, {'id': 'c', 'title': 'Removed', 'type': 'movie'}]
        after = [dict(before[1], episode='2'), before[0], {'id': 'd', 'title': 'Added', 'type': 'movie'}]
        report = app.refresh_report(before, after)
        self.assertEqual(report['added'], ['Added'])
        self.assertEqual(report['removed'], ['Removed'])
        self.assertEqual(report['changed'], ['Pilot'])
        self.assertTrue(report['order_changed'])

    def test_file_refresh_preserves_playlist_corrections_and_manual_matches(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.DATA', Path(folder)):
            old = {'id': 'a', 'type': 'episode', 'title': 'Pilot', 'imdb': 'tt2', 'source_key': 'imdb:tt2:1', 'status': 'missing', 'correction': {'show_tmdb': '10', 'season': '1', 'episode': '2'}, 'plex_override': '99', 'plex_server': 'http://nas'}
            app.save_state({'settings': {}, 'lists': [{'id': 'list', 'name': 'Custom title', 'items': [old], 'source': None, 'playlist': {'key': '7'}}]})
            job_id = app.start_import_job({'list_id': 'list', 'format': 'csv', 'content': 'Const,Title,Title Type\ntt2,Pilot,TV Episode\ntt3,New film,Movie'})['job_id']
            for _ in range(200):
                with app.JOBS_LOCK:
                    job = dict(app.JOBS[job_id])
                if job['status'] != 'running':
                    break
                time.sleep(.01)
            self.assertEqual(job['status'], 'complete', job)
            saved = app.read_state()['lists'][0]
        self.assertEqual(saved['name'], 'Custom title')
        self.assertEqual(saved['items'][0]['id'], 'a')
        self.assertEqual(saved['items'][0]['episode'], '2')
        self.assertEqual(saved['items'][0]['plex_override'], '99')
        self.assertNotIn('metadata_unresolved', saved['items'][0])
        self.assertEqual(saved['refresh_report']['added'], ['New film'])
        self.assertTrue(saved['items'][1]['is_new'])
        self.assertEqual(saved['comparison_baseline'], {'a': 'missing'})
        self.assertTrue(saved['playlist_needs_update'])

    def test_playlist_preview_explains_omissions_and_keeps_repeated_entries(self):
        entry = {'name': 'Mixed', 'items': [
            {'title': 'Film', 'type': 'movie', 'status': 'available', 'plex_keys': ['m']},
            {'title': 'Season', 'type': 'season', 'status': 'partial', 'plex_keys': ['e1', 'e2']},
            {'title': 'Pilot again', 'type': 'episode', 'status': 'available', 'plex_keys': ['e1']},
            {'title': 'Unresolved', 'type': 'episode', 'status': 'unmatched'}]}
        plan = app.playlist_preview(entry)
        self.assertEqual(plan['keys'], ['m', 'e1', 'e2', 'e1'])
        self.assertEqual(plan['entries'][1]['count'], 2)
        self.assertEqual(plan['entries'][3]['status'], 'unmatched')
        self.assertEqual(plan['omitted'], 1)
        self.assertEqual(len(plan['fingerprint']), 64)

    def test_playlist_batches_over_100_preserve_order_and_verify_before_delete(self):
        keys = [str(n) for n in range(1, 106)]
        rows = [{'title': 'Episodes', 'type': 'season', 'status': 'available', 'plex_keys': keys}]
        entry = {'name': 'Long order', 'items': rows, 'playlist': {'key': '999', 'title': 'Old', 'server': 'http://nas'}}
        responses = [ET.fromstring('<MediaContainer><Playlist title="Old"/></MediaContainer>'), ET.fromstring('<MediaContainer machineIdentifier="nas"/>'), ET.fromstring('<MediaContainer><Playlist ratingKey="1000"/></MediaContainer>'), ET.Element('MediaContainer'), ET.fromstring('<MediaContainer totalSize="105">' + ''.join(f'<Video ratingKey="{key}"/>' for key in keys) + '</MediaContainer>'), ET.Element('MediaContainer')]
        with patch('app.compare', return_value=rows), patch('app.remote', side_effect=responses) as remote:
            result = app.create_playlist(entry, {'plex': {'url': 'http://nas', 'key': 'test-token'}}, 'New', True)
        self.assertEqual(result['count'], 105)
        self.assertEqual(remote.call_args_list[3].kwargs['method'], 'PUT')
        self.assertEqual(remote.call_args_list[-1].kwargs['method'], 'DELETE')
