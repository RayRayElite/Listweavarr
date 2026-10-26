import unittest
from unittest.mock import patch

import app
import providers


class TraktTests(unittest.TestCase):
    def item(self, kind, rank, identifier):
        media = {'title': kind.title(), 'number': 2, 'season': 1, 'ids': {'trakt': identifier, 'tmdb': 100 + identifier, 'tvdb': 200 + identifier}}
        return {'id': identifier, 'rank': rank, 'type': kind, kind: media,
                'show': media if kind == 'show' else {'title': 'Parent', 'ids': {'tmdb': 10, 'tvdb': 20}}}

    def headers(self, page, count=3, pages=2):
        return {'x-pagination-page-count': str(pages), 'x-pagination-item-count': str(count), 'x-pagination-page': str(page)}

    def test_all_pages_are_sorted_by_rank_with_exact_tv_scope(self):
        metadata = {'name': 'Mixed', 'item_count': 3, 'updated_at': 'same'}
        responses = [(metadata, {}), ([self.item('episode', 2, 2), self.item('movie', 1, 1)], self.headers(1)), ([self.item('season', 3, 3)], self.headers(2)), (metadata, {})]
        with patch('providers.trakt_get', side_effect=responses):
            result = providers.trakt('https://trakt.tv/users/me/lists/mixed', lambda *a: None, {})
        self.assertEqual([r['type'] for r in result['items']], ['movie', 'episode', 'season'])
        self.assertEqual(result['items'][1]['show_tmdb'], '10')
        self.assertEqual(result['items'][1]['tmdb'], '102')
        self.assertEqual(result['items'][1]['season'], '1')
        self.assertEqual(result['items'][1]['episode'], '2')
        self.assertEqual(result['items'][2]['season'], '2')

    def test_repeated_page_is_rejected(self):
        metadata = {'item_count': 2}
        repeated = [self.item('movie', 1, 1)]
        with patch('providers.trakt_get', side_effect=[(metadata, {}), (repeated, self.headers(1, 2)), (repeated, self.headers(2, 2))]):
            with self.assertRaisesRegex(ValueError, 'unique ranked'):
                providers.trakt('https://trakt.tv/lists/123', lambda *a: None, {})

    def test_gapped_and_tied_ranks_do_not_mean_missing_entries(self):
        metadata={'name':'DC','item_count':3,'updated_at':'same'}
        rows=[self.item('movie',398,3),self.item('season',139,2),self.item('movie',139,1)]
        responses=[(metadata,{}),(rows,self.headers(1,3,1)),(metadata,{})]
        with patch('providers.trakt_get',side_effect=responses):
            result=providers.trakt('https://trakt.tv/lists/123',lambda *a:None,{})
        self.assertEqual([r['source_key'] for r in result['items']],['trakt:1','trakt:2','trakt:3'])
        self.assertIn('tied source ranks',result['warnings'][0])

    def test_list_edit_during_pagination_is_rejected(self):
        responses = [({'item_count': 1, 'updated_at': 'old'}, {}), ([self.item('movie', 1, 1)], self.headers(1, 1, 1)), ({'item_count': 1, 'updated_at': 'new'}, {})]
        with patch('providers.trakt_get', side_effect=responses):
            with self.assertRaisesRegex(ValueError, 'changed during import'):
                providers.trakt('https://trakt.tv/lists/123', lambda *a: None, {})

    def test_stale_total_requires_all_five_categories_to_agree(self):
        metadata={'item_count':2,'updated_at':'same'};item=self.item('movie',1,1)
        responses=[(metadata,{}),([item],self.headers(1,2,1)),([item],self.headers(1,1,1))]+[([],self.headers(1,0,0))]*4+[(metadata,{})]
        with patch('providers.trakt_get',side_effect=responses):
            result=providers.trakt('https://trakt.tv/lists/123',lambda *a:None,{})
        self.assertEqual(len(result['items']),1);self.assertIn('unavailable through the API',result['warnings'][0])

    def test_shortfall_rejected_when_categories_disagree(self):
        item=self.item('movie',1,1);other=self.item('movie',2,2)
        responses=[([other],self.headers(1,1,1))]+[([],self.headers(1,0,0))]*4
        with patch('providers.trakt_get',side_effect=responses):
            with self.assertRaisesRegex(ValueError,'disagree'):providers.verify_trakt_shortfall('/lists/123',[item],{})

    def test_short_category_page_still_rejected(self):
        with patch('providers.trakt_get',return_value=([self.item('movie',1,1)],self.headers(1,2,1))):
            with self.assertRaisesRegex(ValueError,'unique category'):providers.verify_trakt_shortfall('/lists/123',[],{})

    def test_missing_client_id_fails_before_network_access(self):
        with patch('providers.urllib.request.build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'Client ID'):
                providers.trakt_get('/lists/123', {})
        network.assert_not_called()

    def test_redirect_never_forwards_client_id(self):
        with self.assertRaisesRegex(ValueError, 'no credentials were forwarded'):
            providers.TraktRedirects().redirect_request(None, None, 302, '', {}, 'https://example.com')

    def test_public_state_redacts_trakt_key(self):
        state = {'lists': [], 'settings': {'trakt': {'url': 'https://api.trakt.tv', 'key': 'private-registration'}}}
        self.assertNotIn('private-registration', str(app.public_state(state)))

    def test_test_connection_uses_draft_client_id(self):
        with patch('providers.trakt_get') as get:
            self.assertEqual(app.test_connection({'trakt': {'key': 'old'}}, {'service': 'trakt', 'config': {'key': 'draft'}}), {'ok': True})
        self.assertEqual(get.call_args.args[1]['trakt']['key'], 'draft')
