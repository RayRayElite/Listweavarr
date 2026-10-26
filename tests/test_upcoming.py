import datetime
import unittest
from unittest.mock import patch
import explore
import release_watch

class UpcomingTests(unittest.TestCase):
    def test_future_window_excludes_missing_and_released_dates(self):
        today=datetime.date(2026,10,23)
        for date,expected in [('2026-10-24',True),('2026-10-23',False),('2026-10-22',False),('',False),('2028-01-01',False)]:
            self.assertEqual(explore.is_upcoming({'release_date':date},today),expected)

    def test_upcoming_rows_trends_unrated_titles_and_filters(self):
        today=datetime.datetime.now(datetime.timezone.utc).date()
        future=str(today+datetime.timedelta(days=10))
        calls=[]
        def tmdb(path,settings):
            calls.append(path)
            if path.startswith('genre/'):return {'genres':[]}
            if path.startswith('trending/'):
                return {'results':[{'id':1,'title':'Trending future','media_type':'movie','original_language':'en','release_date':future,'vote_count':0}, {'id':2,'title':'Already released','media_type':'movie','original_language':'en','release_date':str(today)}]}
            if path.startswith('discover/movie'):
                return {'results':[{'id':1,'title':'Trending future','original_language':'en','release_date':future,'vote_count':0}, {'id':3,'title':'Other upcoming movie','original_language':'en','release_date':future,'vote_count':0}, {'id':4,'title':'Ignored','original_language':'en','release_date':future,'vote_count':0}, {'id':5,'title':'Other language','original_language':'fr','release_date':future,'vote_count':0}]}
            if path.startswith('discover/tv'):
                return {'results':[{'id':6,'name':'Future series','original_language':'en','first_air_date':future,'vote_count':0}]}
            return {}
        state={'settings':{'tmdb':{'key':'test'}},'lists':[],'explore_languages':['en'],'ignored_titles':[{'tokens':['movie:tmdb:4']}]}
        with patch('providers.cached_tmdb',side_effect=tmdb):
            result=explore.home(state,{'quality':'9.0'},lambda settings:[])
        rows={r['id']:r['items'] for r in result['rows']}
        self.assertEqual([r['tmdb'] for r in rows['trending-upcoming']],['1'])
        self.assertEqual([r['tmdb'] for r in rows['upcoming-movie']],['3'])
        self.assertEqual([r['tmdb'] for r in rows['upcoming-tv']],['6'])
        self.assertIsNone(rows['upcoming-tv'][0]['rating'])
        self.assertTrue(rows['upcoming-tv'][0]['upcoming'])
        self.assertTrue(any(path.startswith('trending/all/week') for path in calls))

    def test_tv_watchlist_transitions_to_premiered_and_rechecks_changed_dates(self):
        with patch('providers.cached_tmdb',return_value={'first_air_date':'2026-11-01'}):
            upcoming=release_watch.tv_availability('1','CA',{},datetime.date(2026,10,23))
            premiered=release_watch.tv_availability('1','CA',{},datetime.date(2026,11,1))
        self.assertEqual(upcoming['status'],'upcoming')
        self.assertEqual(premiered['status'],'premiered')
        with patch('providers.cached_tmdb',return_value={'first_air_date':''}):
            self.assertEqual(release_watch.tv_availability('1','CA',{})['status'],'unknown')
        with patch('release_watch.tv_availability',return_value={'status':'premiered'}):
            checked=release_watch.check([{'id':'CA:show:1','tmdb':'1','type':'show','region':'CA'}],{})
        self.assertEqual(checked['CA:show:1']['status'],'premiered')
