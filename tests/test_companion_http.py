import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import app
import backups
import saved_lists

class CompanionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.data_patch=patch.object(app,'DATA',Path(self.folder.name));self.data_patch.start()
        self.entry={'id':'list','name':'My list','items':[{'id':'one','type':'movie','tmdb':'1','title':'One','status':'missing'}]}
        app.save_state({'settings':{},'lists':[self.entry]})
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.data_patch.stop();self.folder.cleanup()
    def post(self,action,body=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/api/companion/'+action,data=json.dumps(body or {}).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION,'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:return json.load(response)
    def test_recipe_persistence_and_backup(self):
        self.post('recipe-save',{'name':'Space','type':'movie','tags':'space'})
        data=self.post('state');self.assertEqual(data['discovery_recipes'][0]['name'],'Space')
        restored,_=backups.validate(backups.export(app.read_state()),app.normalize)
        self.assertEqual(restored['discovery_recipes'][0]['name'],'Space')
        self.post('recipe-delete',{'id':data['discovery_recipes'][0]['id']})
        self.assertEqual(self.post('state')['discovery_recipes'],[])
    def test_creator_follow_unfollow_and_preferences(self):
        with patch('providers.cached_tmdb',return_value={'id':9,'name':'Verified Person'}):self.post('follow',{'person':'9','role':'crew'})
        self.post('preferences',{'spoiler_safe':True,'muted_inbox':['creators']})
        state=self.post('state');self.assertTrue(state['companion_preferences']['spoiler_safe']);self.assertEqual(state['creator_follows'][0]['name'],'Verified Person')
        self.post('unfollow',{'person':'9'});self.assertEqual(self.post('state')['creator_follows'],[])
    def test_impressions_are_opt_in_and_reset_needs_confirmation(self):
        body={'items':[{'type':'movie','tmdb':'1','title':'One'}]}
        self.post('impressions',body);self.assertFalse(app.read_state().get('discovery_impressions'))
        self.post('preferences',{'log_recommendations':True});self.post('impressions',body)
        self.assertEqual(len(app.read_state()['discovery_impressions']),1)
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('reset-insights')
        error.exception.close()
        self.post('reset-insights',{'confirmed':True});self.assertEqual(app.read_state()['discovery_impressions'],{})
    def test_paths_stale_revision_and_underlying_order(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('path-save',{'list_id':'list','revision':'old','mode':'essential','ids':['one']})
        error.exception.close()
        self.post('path-save',{'list_id':'list','revision':saved_lists.revision(self.entry),'mode':'essential','ids':['one']})
        result=self.post('path',{'list_id':'list','mode':'essential'});self.assertEqual(result['items'][0]['id'],'one')
        self.assertEqual(app.read_state()['lists'][0]['items'],self.entry['items'])
        current=app.read_state()['lists'][0]
        copied=self.post('path-copy',{'list_id':'list','revision':saved_lists.revision(current),'mode':'essential'})['entry']
        self.assertNotEqual(copied['id'],'list');self.assertNotEqual(copied['items'][0]['id'],'one');self.assertEqual(copied['items'][0]['status'],'unchecked')
        self.assertEqual(app.read_state()['lists'][0]['items'],self.entry['items'])
    def test_planning_never_calls_manager_mutations(self):
        with patch('app.arr_call') as call:
            result=self.post('priorities')
            self.assertEqual(len(result['items']),1);call.assert_not_called()

    def test_recommended_order_and_notification_limit_persist(self):
        self.post('path-save',{'list_id':'list','revision':saved_lists.revision(self.entry),'mode':'recommended','ids':['one']})
        self.assertEqual(self.post('path',{'list_id':'list','mode':'recommended'})['items'][0]['id'],'one')
        self.post('preferences',{'notification_limit':10})
        self.assertEqual(self.post('state')['companion_preferences']['notification_limit'],10)
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('preferences',{'notification_limit':900})
        error.exception.close()

    def test_person_search_deduplicates_ids_but_not_distinct_people(self):
        with app.LOCK:
            state=app.read_state();state['creator_follows']=[{'id':'206','name':'Jim Carrey','role':'all'}];app.save_state(state)
        rows=[{'id':206,'name':'Jim Carrey','popularity':99},{'id':206,'name':'Jim Carrey','popularity':99},{'id':999,'name':'Jim Carrey','popularity':1}]
        with patch('providers.cached_tmdb',return_value={'results':rows}):result=self.post('person-search',{'query':'Jim Carrey'})
        self.assertEqual(len(result['items']),2);self.assertEqual(result['items'][0]['following'],'all');self.assertIsNone(result['items'][1]['following'])

    def test_read_one_notification_does_not_dismiss_other_events(self):
        with app.LOCK:
            state=app.read_state();state['requests']=[{'id':str(i),'item':{'title':'Title','type':'movie','tmdb':str(i)},'status':'available'} for i in (1,2)];app.save_state(state)
        with patch('official_lists.document',return_value={'lists':[]}):
            self.post('inbox-read',{'ids':['request:1:available','not-a-real-event']})
            rows=self.post('inbox')['items']
        states={row['id']:row['read'] for row in rows}
        self.assertTrue(states['request:1:available']);self.assertFalse(states['request:2:available'])

