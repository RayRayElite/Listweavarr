import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
import metadata_sources as sources


def claim(value, rank='normal'):
    return {'rank': rank, 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': value}}}


def entity(identifier, title, claims=None):
    return {'id': identifier, 'labels': {'en': {'value': title}}, 'claims': claims or {}}


class MetadataSourceTests(unittest.TestCase):
    def test_transport_rejects_other_hosts_and_credentials(self):
        for url in ['http://www.wikidata.org/x', 'https://evil.example/x', 'https://secret@www.wikidata.org/x']:
            with self.assertRaises(ValueError):
                sources.request_json(url)

    def test_no_redirect_forwards_credentials(self):
        with self.assertRaises(ValueError):
            sources.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_cache_reuses_public_data(self):
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder, patch.object(sources, 'CACHE', Path(folder)):
            fetch = Mock(return_value={'data': 1})
            self.assertEqual(sources.cached('key', fetch), {'data': 1})
            self.assertEqual(sources.cached('key', fetch), {'data': 1})
            fetch.assert_called_once()

    def test_deprecated_claims_and_unknown_snaks_are_ignored(self):
        record = entity('Q1', 'Film', {'P4947': [claim('42'), claim('999', 'deprecated'), {'mainsnak': {'snaktype': 'somevalue'}}]})
        self.assertEqual(sources.wd_row('Q1', record, 'Film')['tmdb'], '42')

    def test_movie_and_show_mapping_conflict_is_not_guessed(self):
        row = sources.wd_row('Q1', entity('Q1', 'Film', {'P4947': [claim('42')], 'P4983': [claim('43')]}), 'Film')
        self.assertIsNone(row['tmdb'])

    def test_wikidata_sequence_uses_explicit_links_not_release_year(self):
        records = {'Q1': entity('Q1', 'Current', {'P155': [claim({'id': 'Q2'})], 'P156': [claim({'id': 'Q3'})]}),
                   'Q2': entity('Q2', 'Earlier', {'P4947': [claim('2')]}), 'Q3': entity('Q3', 'Later', {'P4947': [claim('3')]})}
        with patch.object(sources, 'wd_entity', side_effect=records.__getitem__):
            result = sources.wikidata('Q1')
        self.assertEqual([r['title'] for r in result['sequence']], ['Earlier', 'Current', 'Later'])
        self.assertIn('does not establish story chronology', result['sequence_note'])

    def test_ambiguous_sequence_is_never_flattened(self):
        record = entity('Q1', 'Current', {'P155': [claim({'id': 'Q2'}), claim({'id': 'Q3'})]})
        with patch.object(sources, 'wd_entity', return_value=record):
            result = sources.wikidata('Q1')
        self.assertEqual(result['sequence'], [])
        self.assertIn('branches or conflicts', result['notes'][0])

    def test_qualifier_sequence_links_are_supported(self):
        statement = claim({'id': 'Q10'})
        statement['qualifiers'] = {'P156': [{'datavalue': {'value': {'id': 'Q2'}}}]}
        self.assertEqual(sources.series_neighbors(entity('Q1', 'Film', {'P179': [statement]}), 'P156'), ['Q2'])

    def test_anilist_relations_keep_season_scope_and_do_not_guess_tmdb(self):
        data = {'data': {'Media': {'title': {'english': 'Anime', 'native': '日本語'}, 'episodes': 12, 'averageScore': 82,
                                 'relations': {'edges': [{'relationType': 'SEQUEL', 'node': {'id': 2, 'type': 'ANIME', 'title': {'english': 'Next season'}}}]}}}}
        with patch.object(sources, 'cached', return_value=data):
            result = sources.anilist(1)
        self.assertEqual(result['connections'][0]['relationship'], 'Sequel')
        self.assertNotIn('tmdb', result['connections'][0])
        self.assertEqual(result['connections'][0]['url'], 'https://anilist.co/anime/2')
        self.assertIn('individual seasons', result['notes'][0])

    def test_optional_provider_failure_preserves_other_metadata(self):
        with patch('providers.cached_tmdb', return_value={'wikidata_id': 'Q1'}), patch.object(sources, 'wikidata', side_effect=ValueError('Unavailable')):
            result = sources.enrich('movie', '1', {})
        self.assertEqual(result['sources'][0]['status'], 'unavailable')
        self.assertEqual(result['sources'][2]['status'], 'not connected')

    def test_missing_cross_reference_never_searches_by_title(self):
        with patch('providers.cached_tmdb', return_value={}), patch.object(sources, 'request_json') as request:
            result = sources.enrich('movie', '1', {})
        request.assert_not_called()
        self.assertEqual(result['sources'][0]['status'], 'unmatched')

    def test_conflicting_reverse_cross_reference_is_rejected(self):
        wd = {'provider': 'Wikidata', 'status': 'matched', 'identity': {'type': 'movie', 'tmdb': '999'}, 'anilist_id': '1'}
        with patch('providers.cached_tmdb', return_value={'wikidata_id': 'Q1'}), patch.object(sources, 'wikidata', return_value=wd), patch.object(sources, 'anilist') as anime:
            result = sources.enrich('movie', '1', {})
        self.assertEqual(result['sources'][0]['status'], 'unmatched')
        anime.assert_not_called()

    def test_enrichment_rejects_episode_or_untrusted_identifiers(self):
        with patch('providers.cached_tmdb') as lookup:
            for kind, identifier in [('episode', '1'), ('movie', '../secret'), ('show', '0')]:
                with self.assertRaises(ValueError):
                    sources.enrich(kind, identifier, {})
        lookup.assert_not_called()

    def test_custom_tvdb_lists_never_establish_franchise(self):
        data = {'name': 'Film', 'lists': [{'id': 3, 'isOfficial': False}]}
        with patch.object(sources, 'tvdb_call', side_effect=[[{'movie': {'id': 1}}], data]) as call:
            result = sources.tvdb('movie', {'imdb_id': 'tt123'}, {})
        self.assertEqual(result['franchise'], [])
        self.assertEqual(call.call_count, 2)

    def test_tvdb_official_list_maps_movie_tv_separately(self):
        responses = [{'lists': [{'id': 3, 'name': 'Franchise', 'isOfficial': True}]},
                     {'isOfficial': True, 'entities': [{'movieId': 5, 'order': 1}]},
                     {'name': 'Film', 'remoteIds': [{'sourceName': 'TheMovieDB.com', 'id': '7'}]}]
        with patch.object(sources, 'tvdb_call', side_effect=responses):
            result = sources.tvdb('show', {'tvdb_id': 1}, {})
        self.assertEqual(result['franchise'][0]['key'], 'movie:7')

    def test_tvdb_test_uses_draft_key_and_pin_without_saving(self):
        settings = {'tvdb': {'key': 'old', 'pin': 'old-pin'}}
        with patch.object(sources, 'tvdb_call') as call:
            app.test_connection(settings, {'service': 'tvdb', 'config': {'key': 'draft', 'pin': 'draft-pin'}})
        self.assertEqual(call.call_args.args[1]['tvdb']['pin'], 'draft-pin')
        self.assertEqual(settings['tvdb']['key'], 'old')
        public = app.public_state({'settings': settings, 'lists': []})
        self.assertNotIn('pin', public['settings']['tvdb'])
        self.assertNotIn('key', public['settings']['tvdb'])


if __name__ == '__main__':
    unittest.main()
