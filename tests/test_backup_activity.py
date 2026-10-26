import copy
import json
import tempfile
import unittest
from pathlib import Path
import app
import backups
import activity

class BackupTests(unittest.TestCase):
    def state(self):
        return {'settings':{'plex':{'key':'SECRET'}},'plex_auth':{'token':'SECRET'},'lists':[{'id':'one','name':'Mixed','items':[{'id':'movie','type':'movie','title':'Movie','tmdb':'1','status':'available','plex_keys':['20']},{'id':'episode','type':'episode','title':'Episode','show_tvdb':'2','season':'1','episode':'3','correction':{'imdb':'tt12'}}]}],'ignored_titles':[{'id':'ignored','title':'Ignore','tokens':['movie:tmdb:8']}],'rating_preferences':{'main':'imdb','display':'all'}}

    def test_portable_redaction_and_roundtrip_scope(self):
        state=self.state();state['lists'][0]['source']='https://user:SECRET@example.test/list?apikey=SECRET&sort=rank'
        document=backups.export(state)
        self.assertNotIn('SECRET',json.dumps(document))
        data,summary=backups.validate(document,app.normalize)
        self.assertEqual(summary['items'],2)
        restored=backups.restore({'settings':{'plex':{'key':'KEPT'}},'lists':[]},data,'replace')
        self.assertEqual(restored['settings']['plex']['key'],'KEPT')
        self.assertEqual([r['type'] for r in restored['lists'][0]['items']],['movie','episode'])
        self.assertEqual(restored['lists'][0]['items'][1]['episode'],'3')
        self.assertEqual(restored['lists'][0]['items'][1]['correction']['imdb'],'tt12')
        self.assertEqual(restored['lists'][0]['items'][0]['status'],'unchecked')
        self.assertNotIn('plex_keys',restored['lists'][0]['items'][0])

    def test_merge_does_not_overwrite_current_list(self):
        state=self.state();data=backups.export(state)['data'];data['lists'][0]['name']='Incoming'
        restored=backups.restore(state,data,'merge')
        self.assertEqual(restored['lists'][0]['name'],'Mixed')
        self.assertEqual(len(restored['lists']),1)
        self.assertEqual(state['lists'][0]['items'][0]['status'],'available')

    def test_invalid_backup_rejected(self):
        for document in ({'format':'bad','version':1,'data':{}},{'format':'reelcheck-workspace','version':8,'data':{}},{'format':'reelcheck-workspace','version':1,'data':{'lists':[{'id':'one','name':'Bad','items':[{'id':'1','type':'episode','title':'Missing numbering'}]}]}}):
            with self.assertRaises(ValueError):backups.validate(document,app.normalize)

    def test_rolling_backup_retention_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(12):backups.rolling(Path(folder),self.state())
            files=list(Path(folder).glob('*.json'))
            self.assertEqual(len(files),10)
            self.assertTrue(all('SECRET' not in p.read_text() for p in files))

class ActivityTests(unittest.TestCase):
    def setUp(self):activity._cache.clear()

    def settings(self):return {'radarr':{'key':'test','url':'http://radarr'},'sonarr':{'key':'test','url':'http://sonarr'}}

    def test_download_import_and_plex_are_distinct(self):
        queue=[{'movieId':1,'status':'downloading','size':100,'sizeleft':25}]
        def call(settings,service,path):
            if path=='movie':return [{'id':1,'tmdbId':10,'hasFile':False}]
            return {'records':queue,'totalRecords':len(queue)}
        row={'id':'m','type':'movie','tmdb':'10','status':'missing'}
        result=activity.summarize([row],self.settings(),call)['items']['m']
        self.assertEqual(result['state'],'downloading');self.assertEqual(result['percent'],75)
        self.assertTrue(result['prevent_duplicate'])
        queue[0]['status']='completed';activity._cache.clear()
        self.assertEqual(activity.summarize([row],self.settings(),call)['items']['m']['state'],'importing')
        queue[0]['trackedDownloadStatus']='warning';activity._cache.clear()
        self.assertEqual(activity.summarize([row],self.settings(),call)['items']['m']['state'],'import_blocked')
        row['status']='available'
        self.assertEqual(activity.summarize([row],self.settings(),call)['items']['m']['state'],'available')

    def test_episode_scope_and_unknown_ids_never_match_whole_show(self):
        def call(settings,service,path):
            if path=='series':return [{'id':1,'tvdbId':20}]
            if path.startswith('episode?'):return [{'id':101,'seasonNumber':1,'episodeNumber':1,'airDateUtc':'2020-01-01','hasFile':True},{'id':102,'seasonNumber':1,'episodeNumber':2,'airDateUtc':'2020-01-02','hasFile':False}]
            return {'records':[{'seriesId':1,'episodeId':102,'status':'downloading','size':100,'sizeleft':50}],'totalRecords':1}
        rows=[{'id':'one','type':'episode','show_tvdb':'20','season':'1','episode':'1'},{'id':'two','type':'episode','show_tvdb':'20','season':'1','episode':'2'},{'id':'unknown','type':'show'}]
        result=activity.summarize(rows,self.settings(),call)['items']
        self.assertEqual(result['one']['state'],'downloaded')
        self.assertEqual(result['two']['state'],'downloading')
        self.assertEqual(result['unknown']['state'],'not_managed')

    def test_progress_failure_does_not_claim_missing(self):
        def call(*args):raise ValueError('Unavailable')
        result=activity.summarize([{'id':'m','type':'movie','tmdb':'10'}],self.settings(),call)
        self.assertEqual(result['items']['m']['state'],'unavailable')
        self.assertTrue(result['warnings'])

class BackupHTTPTests(unittest.TestCase):
    def test_preview_is_required_and_restore_retains_connections(self):
        import threading
        import urllib.request
        import urllib.error
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder,patch.object(app,'DATA',Path(folder)):
            app.save_state({'settings':{'plex':{'key':'keep-token'}},'lists':[]})
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            document=backups.export({'settings':{'plex':{'key':'not-restored'}},'lists':[{'id':'list','name':'Saved','items':[{'id':'m','type':'movie','title':'Test','tmdb':'1'}]}]})
            def post(path,body):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/backup/'+path,data=json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION})
                with urllib.request.urlopen(req) as response:return json.load(response)
            try:
                with self.assertRaises(urllib.error.HTTPError) as rejected:post('restore',{'document':document,'mode':'replace'})
                rejected.exception.close()
                preview=post('preview',{'document':document})
                self.assertEqual(app.read_state()['lists'],[])
                result=post('restore',{'document':document,'fingerprint':preview['fingerprint'],'mode':'replace'})
                self.assertEqual(result['lists'][0]['name'],'Saved')
                self.assertEqual(app.read_state()['settings']['plex']['key'],'keep-token')
                self.assertTrue(list((Path(folder)/'backups').glob('*.json')))
                local_files=post('list',{})['files']
                local_preview=post('preview',{'file':local_files[0]})
                self.assertEqual(local_preview['summary']['lists'],0)
                self.assertNotIn('keep-token',json.dumps(post('export',{})))
            finally:
                server.shutdown();server.server_close();thread.join()

class DuplicateRequestTests(unittest.TestCase):
    def test_queued_movie_does_not_submit_another_search(self):
        from unittest.mock import patch
        calls=[]
        def call(settings,service,path,payload=None,method=None):
            calls.append((path,payload))
            if path=='qualityprofile':return [{'id':1}]
            if path=='rootfolder':return [{'path':'/movies'}]
            if path=='movie':return [{'id':1,'tmdbId':10,'hasFile':False}]
            if path.startswith('queue?'):return {'records':[{'movieId':1,'status':'downloading'}],'totalRecords':1}
            raise AssertionError('Unexpected write: '+path)
        activity._cache.clear()
        with patch('app.arr_call',side_effect=call):
            result=app.request_item({'type':'movie','tmdb':'10','title':'Queued'}, {'radarr':{'url':'http://radarr','key':'key'}},1,'/movies')
        self.assertIn('no duplicate search',result)
        self.assertTrue(all(payload is None for path,payload in calls))
