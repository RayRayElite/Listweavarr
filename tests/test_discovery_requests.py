import copy
import datetime
import unittest
from unittest.mock import patch
import cult_discovery
import indexer_discovery
import request_ledger
import explore

class DiscoveryAndRequestsTests(unittest.TestCase):
    def test_bad_rating_is_not_fun_evidence(self):
        base={'vote_average':3,'vote_count':1000,'release_date':'1990-01-01','keywords':{'keywords':[]}}
        self.assertIsNone(cult_discovery.score(base,4))
        cult=copy.deepcopy(base);cult['keywords']['keywords']=[{'name':'cult film'}]
        self.assertIsNone(cult_discovery.score(cult))
        cult['keywords']['keywords'].append({'name':'campy'})
        self.assertIsNone(cult_discovery.score(cult,2))
        cult['enjoyable_bad_reviews']=1
        scored=cult_discovery.score(cult,2)
        self.assertIsNotNone(scored);self.assertTrue(any('2 established' in r for r in scored['reasons']))
        cult['adult']=True;self.assertIsNone(cult_discovery.score(cult,2))
        cult['adult']=False;cult['release_date']='2099-01-01';self.assertIsNone(cult_discovery.score(cult,2))

    def test_canonical_keywords_and_review_authors(self):
        movie={'vote_average':3,'vote_count':300,'release_date':'1990-01-01','keywords':{'keywords':[{'name':"so bad it"+chr(0x2019)+"s good"}]}}
        self.assertIsNotNone(cult_discovery.score(movie))
        self.assertEqual(cult_discovery.review_evidence([{'author':'A','content':"so bad it's good"},{'author':'A','content':'hilariously bad'},{'author':'B','content':'not so bad it is good'},{'author':'C','content':'A bad movie.'},{'author':'D','content':'so bad it is not good'}]),1)

    def test_critic_audience_split_is_supporting_evidence(self):
        movie={'vote_average':4.7,'vote_count':1000,'release_date':'1990-01-01','keywords':{'keywords':[{'name':'campy'},{'name':'b-movie'}]}}
        self.assertIsNone(cult_discovery.score(movie))
        result=cult_discovery.score(movie,support=2,extra={'ratings':[{'source':'tomatoes','value':20},{'source':'popcorn','value':70}]})
        self.assertIsNotNone(result);self.assertTrue(any('50 points' in r for r in result['reasons']))
        movie['vote_count']=2;self.assertIsNone(cult_discovery.score(movie,4))

    def test_indexer_sample_deduplicates_releases_and_never_grabs(self):
        indexer_discovery._cache.clear()
        records=[{'tmdbId':1,'seeders':100,'categories':[{'id':2000}]},{'tmdbId':1,'seeders':50,'categories':[{'id':2000}]},{'tmdbId':1,'seeders':80,'categories':[{'id':5000}]},{'title':'Ambiguous title','seeders':500,'categories':[{'id':2000}]},{'tmdbId':2,'seeders':'unknown','categories':[{'id':2000}]}]
        def metadata(path,settings):return {'id':1,'title':'Film','name':'Show','vote_average':8,'vote_count':1000}
        cfg={'prowlarr':{'url':'http://prowlarr','key':'private'},'tmdb':{'key':'private'}}
        with patch('providers.cached_tmdb',side_effect=metadata),patch('indexer_discovery.time.time',return_value=10):
            calls=[]
            def call(*args,**kwargs):calls.append(args);return records
            rows,warnings=indexer_discovery.candidates(cfg,call)
            cached,_=indexer_discovery.candidates(cfg,call)
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['seeders'],100)
        self.assertEqual({r['kind'] for r in rows},{'movie','show'})
        self.assertEqual(len(calls),1);self.assertIn('/api/v1/search?',calls[0][1]);self.assertTrue(any('not a worldwide' in w for w in warnings))
        self.assertNotIn('downloadUrl',str(rows));self.assertNotIn('private',str(rows))

    def test_optional_shelves_filter_ownership_ignores_language_quality(self):
        records=[{'kind':'movie','seeders':100,'details':{'id':1,'title':'Owned','vote_average':8,'vote_count':1000,'original_language':'en'}},{'kind':'movie','seeders':90,'details':{'id':2,'title':'Bad','vote_average':2,'vote_count':1000,'original_language':'en'}},{'kind':'show','seeders':80,'details':{'id':3,'name':'Foreign','vote_average':8,'vote_count':1000,'original_language':'fr'}},{'kind':'movie','seeders':70,'details':{'id':4,'title':'New','vote_average':8,'vote_count':1000,'original_language':'en'}}]
        state={'settings':{'tmdb':{'key':'x'},'plex':{'key':'x'}},'lists':[],'explore_languages':['en']}
        catalog=[{'type':'movie','title':'Owned','year':'2020','ids':{'tmdb':'1'}}]
        with patch('indexer_discovery.candidates',return_value=(records,[])),patch.object(explore,'library',return_value=(catalog,True)):
            result=explore.extra_shelf(state,{'shelf':'indexers'},lambda s:catalog,lambda *a:None)
        self.assertEqual([r['title'] for r in result['rows'][0]['items']],['New'])

    def test_request_scope_and_failure_and_notification_idempotency(self):
        state={};episode={'type':'episode','title':'Pilot','show_tvdb':'123','season':'1','episode':'1'}
        pending=request_ledger.record(state,episode)
        request_ledger.record(state,episode,status='failed',message='Manager offline')
        request_ledger.record(state,episode) # opening another review must not erase the error
        self.assertEqual(pending['status'],'failed')
        second=dict(episode,episode='2');request_ledger.record(state,second,status='requested')
        self.assertEqual(len(state['requests']),2)
        request_ledger.apply_status(state,{pending['id']:{'state':'available','label':'Available in Plex'}})
        request_ledger.apply_status(state,{pending['id']:{'state':'available','label':'Available in Plex'}})
        self.assertEqual(len(state['request_notifications']),1)
        self.assertEqual(pending['status'],'available')
        request_ledger.apply_status(state,{pending['id']:{'state':'unavailable','label':'Manager offline'}})
        self.assertEqual(pending['status'],'available');self.assertEqual(pending['check_warning'],'Manager offline')
        self.assertEqual(state['requests'][1]['status'],'requested')


class RequestApiTests(unittest.TestCase):
    def test_failed_request_retry_confirmation_and_available_notice(self):
        import json,tempfile,threading,urllib.request,urllib.error
        from pathlib import Path
        import app
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder,patch.object(app,'DATA',Path(folder)):
            app.save_state({'settings':{},'lists':[{'id':'list','name':'List','items':[{'id':'movie','type':'movie','title':'Film','tmdb':'1','status':'missing'}]}]})
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(path,body):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/'+path,data=json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION})
                with urllib.request.urlopen(req) as result:return json.load(result)
            try:
                with patch.object(app,'request_item',side_effect=ValueError('Manager unavailable')):
                    post('request',{'list_id':'list','ids':['movie'],'options':{'radarr':{'profile':'1','root':'/media'}}})
                ledger=post('requests/list',{})['items']
                self.assertEqual(len(ledger),1);self.assertEqual(ledger[0]['status'],'failed')
                with patch.object(app,'request_item',return_value='Search submitted') as submit:
                    with self.assertRaises(urllib.error.HTTPError) as rejected:post('requests/retry',{'id':ledger[0]['id']})
                    rejected.exception.close()
                    submit.assert_not_called()
                    retried=post('requests/retry',{'id':ledger[0]['id'],'confirmed':True,'profile':'1','root':'/media'})
                    self.assertEqual(retried['items'][0]['status'],'requested');submit.assert_called_once()
                with patch('activity.summarize',return_value={'items':{ledger[0]['id']:{'state':'available','label':'Available in Plex'}},'warnings':[]}):
                    ready=post('requests/refresh',{})
                    self.assertEqual(ready['items'][0]['status'],'available');self.assertEqual(len(ready['notifications']),1)
                    again=post('requests/refresh',{})
                    self.assertEqual(len(again['notifications']),1)
                self.assertTrue(post('requests/acknowledge',{})['notifications'][0]['read'])
            finally:server.shutdown();server.server_close();thread.join()
