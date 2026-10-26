import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import explore
import ratings
import official_lists


class BrowseNavigationTests(unittest.TestCase):
    def test_rating_order_preserves_main_and_appends_new_sources(self):
        prefs=ratings.preferences({'main':'imdb','display':['imdb','tmdb'],'order':['tmdb','imdb']})
        self.assertEqual(prefs['main'],'imdb')
        self.assertEqual(prefs['order'][:2],['tmdb','imdb'])
        self.assertEqual(set(prefs['order']),set(ratings.SOURCES))
        for order in (['imdb','imdb'],['unknown'],'imdb'):
            with self.assertRaises(ValueError):ratings.preferences({'order':order})

    def test_shelf_pages_advance_upstream_without_dropping_results(self):
        paths=[]
        def tmdb(path,settings):
            paths.append(path)
            if path.startswith('genre/'):return {'genres':[]}
            query=parse_qs(urlsplit(path).query)
            if path.startswith('discover/movie?'):
                page=int(query['page'][0])
                return {'results':[{'id':page*100+i,'title':'Movie '+str(page*100+i),'vote_average':8,'vote_count':500,'release_date':'2020-01-01','original_language':'en'} for i in range(20)],'total_pages':6}
            raise AssertionError('Unrelated shelf queried: '+path)
        state={'settings':{'tmdb':{'key':'test'}},'lists':[],'explore_languages':['en']}
        with patch.object(explore,'library',return_value=([],True)),patch('providers.cached_tmdb',side_effect=tmdb):
            first=explore.home(state,{'type':'movie','shelf':'gems','page':1},None)
            second=explore.home(state,{'type':'movie','shelf':'gems','page':2},None)
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual(len(first['rows'][0]['items']),60)
        self.assertEqual(len(second['rows'][0]['items']),60)
        self.assertTrue(set(r['tmdb'] for r in first['rows'][0]['items']).isdisjoint(r['tmdb'] for r in second['rows'][0]['items']))
        self.assertEqual([int(parse_qs(urlsplit(p).query)['page'][0]) for p in paths if p.startswith('discover/')],[1,2,3,4,5,6])

    def test_failed_shelf_page_can_be_retried_instead_of_ending_results(self):
        def tmdb(path,settings):
            if path.startswith('genre/'):return {'genres':[]}
            raise ValueError('Temporarily unavailable')
        with patch.object(explore,'library',return_value=([],True)),patch('providers.cached_tmdb',side_effect=tmdb):
            with self.assertRaisesRegex(ValueError,'Temporarily unavailable'):
                explore.home({'settings':{'tmdb':{'key':'test'}}},{'type':'movie','shelf':'gems','page':2},None)

    def test_official_catalogue_contains_curated_portable_lists(self):
        data=official_lists.catalogue()
        self.assertEqual(data['sources'],[])
        self.assertTrue(data['lists'])
        self.assertEqual(len({r['id'] for r in data['lists']}),len(data['lists']))
        self.assertTrue(all(r['kind']=='curated' and r['count']>0 and 'items' not in r for r in data['lists']))
        with self.assertRaises(ValueError):official_lists.collection_id('mcu')
