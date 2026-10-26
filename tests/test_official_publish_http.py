import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import app
import official_lists
import saved_lists

class OfficialPublishHTTPTests(unittest.TestCase):
    def setUp(self):
        self.curator_patch=patch.dict('os.environ',{'REELCHECK_CURATOR_MODE':'1'});self.curator_patch.start()
        self.folder=tempfile.TemporaryDirectory()
        self.data_patch=patch.object(app,'DATA',Path(self.folder.name)/'data');self.data_patch.start()
        self.catalogue_patch=patch.object(official_lists,'ROOT',Path(self.folder.name)/'catalogue');self.catalogue_patch.start()
        self.entry={'id':'personal','name':'Example','source':None,'items':[{'id':'one','type':'movie','tmdb':'1','title':'One','status':'available'}]}
        app.save_state({'settings':{},'lists':[self.entry]})
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.catalogue_patch.stop();self.data_patch.stop();self.folder.cleanup();self.curator_patch.stop()
    def post(self,body,path='publish'):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/api/explore/official/'+path,data=json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION,'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:return json.load(response)
    def test_publish_requires_confirmation_and_fresh_revision(self):
        for body in ({'list_id':'personal','revision':saved_lists.revision(self.entry)}, {'list_id':'personal','confirmed':True,'revision':'stale'}):
            with self.assertRaises(urllib.error.HTTPError):self.post(body)
        self.assertEqual(official_lists.document()['lists'],[])
        result=self.post({'list_id':'personal','confirmed':True,'revision':saved_lists.revision(self.entry)})
        self.assertTrue(result['entry']['official_authoring'])
        self.assertEqual(len(official_lists.document()['lists']),1)
        self.assertEqual(app.read_state()['lists'][0]['items'],self.entry['items'])
        second=self.post({'list_id':'personal','confirmed':True,'revision':saved_lists.revision(result['entry'])})
        self.assertFalse(second['report']['changed']);self.assertEqual(second['report']['version'],1)
    def test_state_write_failure_rolls_catalogue_back(self):
        with patch.object(app,'save_state',side_effect=OSError('test failure')):
            with self.assertRaises(urllib.error.HTTPError):self.post({'list_id':'personal','confirmed':True,'revision':saved_lists.revision(self.entry)})
        self.assertEqual(official_lists.document()['lists'],[])
        self.assertNotIn('official_authoring',app.read_state()['lists'][0])

    def install_update(self):
        self.entry.update(official_id='example',official_version=1)
        app.save_state({'settings':{},'lists':[self.entry]})
        official_lists.write_document({'version':2,'lists':[{'id':'example','version':2,'name':'Updated','description':'','poster':'','items':[{'type':'movie','tmdb':'2','title':'Two'}]}]})

    def test_update_preview_confirmation_skip_and_rollback(self):
        self.install_update()
        pending=self.post({},'updates')['lists']
        self.assertEqual(len(pending),1)
        body=dict(list_id='personal',revision=pending[0]['revision'],version=2,mode='merge')
        with self.assertRaises(urllib.error.HTTPError) as error:self.post(body,'update')
        error.exception.close()
        updated=self.post(dict(body,confirmed=True),'update')['entry']
        self.assertEqual([row['tmdb'] for row in updated['items']],['2','1'])
        self.assertEqual(len(self.post({},'updates')['recent']),1)
        restored=self.post(dict(list_id='personal',revision=saved_lists.revision(updated),version=2,confirmed=True),'rollback')['entry']
        self.assertEqual([row['tmdb'] for row in restored['items']],['1'])
        self.post(dict(list_id='personal',revision=saved_lists.revision(restored),version=2),'skip')
        self.assertEqual(self.post({},'updates')['lists'],[])

    def test_health_needs_no_official_link_and_update_rejects_stale_catalogue(self):
        report=self.post({'list_id':'personal'},'health')
        self.assertEqual(report['entries'],1);self.assertEqual(report['total'],0)
        self.install_update()
        with self.assertRaises(urllib.error.HTTPError) as error:self.post(dict(list_id='personal',revision=saved_lists.revision(self.entry),version=1,confirmed=True),'update')
        error.exception.close()
        self.assertEqual(app.read_state()['lists'][0]['official_version'],1)

    def test_feed_preview_install_and_personal_list_separation(self):
        incoming={'format':'reelcheck-official-catalogue','version':1,'lists':[{'id':'new','version':1,'name':'New official','description':'','poster':'','items':[{'type':'movie','title':'Title','tmdb':'1'}]}]}
        preview=self.post({'document':incoming},'feed-preview')
        self.assertEqual(official_lists.document()['lists'],[])
        with self.assertRaises(urllib.error.HTTPError) as error:self.post({'token':preview['token']},'feed-install')
        error.exception.close()
        result=self.post({'token':preview['token'],'confirmed':True},'feed-install')
        self.assertEqual(len(result['summary']['added']),1)
        self.assertEqual(app.read_state()['lists'][0],self.entry)
        self.assertEqual(self.post({},'feed-export')['lists'][0]['name'],'New official')

    def test_feed_stale_preview_cannot_overwrite_new_publication(self):
        incoming={'format':'reelcheck-official-catalogue','version':1,'lists':[{'id':'new','version':1,'name':'New','items':[{'type':'movie','title':'Title','tmdb':'1'}]}]}
        preview=self.post({'document':incoming},'feed-preview')
        self.post({'list_id':'personal','confirmed':True,'revision':saved_lists.revision(self.entry)})
        with self.assertRaises(urllib.error.HTTPError) as error:self.post({'token':preview['token'],'confirmed':True},'feed-install')
        error.exception.close()
        self.assertEqual(len(official_lists.document()['lists']),1)
        self.assertNotEqual(official_lists.document()['lists'][0]['id'],'new')

    def test_non_curator_cannot_publish(self):
        with patch.dict('os.environ',{'REELCHECK_CURATOR_MODE':'0'}):
            with self.assertRaises(urllib.error.HTTPError) as caught:self.post({'list_id':'personal','confirmed':True})
            self.assertIn('disabled',caught.exception.read().decode())
        self.assertEqual(official_lists.document()['lists'],[])

    def test_update_check_reads_manifest_without_installing_catalogue(self):
        with app.LOCK:
            state=app.read_state();state['official_feed_url']='https://example.com/official-lists.json';app.save_state(state)
        manifest={'format':'reelcheck-catalogue-manifest','version':3,'lists':[{'id':'one','name':'One','version':2,'count':5}]}
        with patch('catalogue_feed.download',return_value=manifest) as download,patch.dict('os.environ',{'REELCHECK_CURATOR_MODE':'0'}):
            result=self.post({},'feed-check')
        self.assertEqual(result['count'],1)
        download.assert_called_once_with('https://example.com/official-lists.manifest.json')
        self.assertEqual(official_lists.document()['lists'],[])
        self.assertEqual(app.read_state()['official_feed_available']['version'],3)
