import datetime
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
import app
import explore
import release_watch

class ReleaseTests(unittest.TestCase):
    def test_regional_dates_and_future_home_release(self):
        dates={'results':[{'iso_3166_1':'CA','release_dates':[{'type':3,'release_date':'2026-10-01T00:00:00Z'},{'type':4,'release_date':'2026-11-01T00:00:00Z'}]},{'iso_3166_1':'US','release_dates':[{'type':4,'release_date':'2026-10-10T00:00:00Z'}]}]}
        with patch('providers.cached_tmdb',return_value=dates):
            ca=release_watch.availability('1','CA',{},datetime.date(2026,10,23))
            us=release_watch.availability('1','US',{},datetime.date(2026,10,23))
            unknown=release_watch.availability('1','GB',{},datetime.date(2026,10,23))
        self.assertEqual(ca['status'],'theatrical')
        self.assertEqual(ca['expected_home_date'],'2026-11-01')
        self.assertEqual(us['status'],'home')
        self.assertEqual(unknown['status'],'unknown')

    def test_disc_also_qualifies_and_bad_dates_are_ignored(self):
        with patch('providers.cached_tmdb',return_value={'results':[{'iso_3166_1':'CA','release_dates':[{'type':5,'release_date':'2020-01-01'},{'type':4,'release_date':'bad'}]}]}):
            result=release_watch.availability('1','CA',{})
        self.assertEqual(result['status'],'home')
        self.assertEqual(result['home_format'],'Disc')

    def test_discovery_queries_and_classification(self):
        calls=[]
        today=str(datetime.datetime.now(datetime.timezone.utc).date())
        def tmdb(path,settings):
            calls.append(path)
            if path.startswith('genre/'):return {'genres':[]}
            if path.startswith('discover/'):
                from urllib.parse import urlsplit,parse_qs
                params=parse_qs(urlsplit(path).query)
                if params.get('with_release_type')==['2|3']:
                    return {'results':[{'id':1,'title':'Cinema','vote_average':8,'vote_count':100},{'id':2,'title':'Already home','vote_average':8,'vote_count':100}]}
                if params.get('with_release_type')==['4|5']:
                    return {'results':[{'id':2,'title':'Already home','vote_average':8,'vote_count':100}]}
                return {'results':[]}
            if path.endswith('/release_dates'):
                return {'results':[{'iso_3166_1':'CA','release_dates':[{'type':3,'release_date':today}]+([{'type':4,'release_date':today}] if path.startswith('movie/2/') else [])}]}
            return {}
        with patch('providers.cached_tmdb',side_effect=tmdb):
            result=explore.home({'settings':{'tmdb':{'key':'test'}},'lists':[]},{'type':'movie','region':'CA'},lambda settings:[])
        rows={r['id']:r['items'] for r in result['rows']}
        self.assertEqual([r['tmdb'] for r in rows['recent-theatrical']],['1'])
        self.assertEqual([r['tmdb'] for r in rows['recent-home']],['2'])
        self.assertTrue(any('region=CA' in path and 'release_date.gte=' in path for path in calls))

    def test_watchlist_persistence_transition_acknowledgement_and_removal(self):
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder,patch.object(app,'DATA',Path(folder)):
            app.save_state({'settings':{},'lists':[]})
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(action,body={}):
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/releases/'+action,data=json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION})
                with urllib.request.urlopen(request) as response:return json.load(response)
            try:
                with patch('providers.cached_tmdb',return_value={'title':'Movie'}),patch('release_watch.availability',return_value={'status':'theatrical','region':'CA'}),patch.object(app,'request_item') as downloads:
                    saved=post('add',{'tmdb':'1','region':'CA'})
                    post('add',{'tmdb':'1','region':'CA'})
                    self.assertEqual(len(app.read_state()['release_watchlist']),1)
                    with patch('release_watch.check',return_value={'CA:1':{'status':'home','home_date':'2026-10-23','home_format':'Digital'}}):
                        checked=post('check')
                    self.assertEqual(checked['items'][0]['status'],'home')
                    self.assertFalse(checked['items'][0]['acknowledged'])
                    self.assertTrue(post('acknowledge',{'id':'CA:1'})['items'][0]['acknowledged'])
                    self.assertEqual(post('remove',{'id':'CA:1'})['items'],[])
                    with patch('release_watch.tv_availability',return_value={'status':'upcoming','region':'CA','premiere_date':'2027-01-01'}):
                        tv=post('add',{'tmdb':'1','type':'show','region':'CA'})
                    self.assertEqual(tv['items'][0]['id'],'CA:show:1')
                    self.assertEqual(tv['items'][0]['type'],'show')
                    post('remove',{'id':'CA:show:1'})
                    downloads.assert_not_called()
                self.assertEqual(app.read_state()['lists'],[])
            finally:
                server.shutdown();server.server_close();thread.join()
