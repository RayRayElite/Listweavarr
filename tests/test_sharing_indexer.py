import copy
import unittest
from unittest.mock import patch
import app,indexer_discovery as ix,list_sharing

class SharingAndIndexerTests(unittest.TestCase):
    def test_shared_list_whitelists_private_state_and_preserves_order_scope(self):
        entry={'id':'private-list','name':'Mixed order','description':'A collection','source':'https://private.example?token=secret','playlist':{'key':'secret'},'items':[{'id':'private1','type':'episode','title':'Pilot','show_tmdb':'2','season':'1','episode':'1','status':'available','plex_key':'secret','request_log':{'token':'secret'},'source_url':'https://private.example'},{'id':'private2','type':'movie','title':'Film','tmdb':'1','status':'missing'}]}
        document=list_sharing.export(entry)
        text=str(document)
        self.assertNotIn('secret',text);self.assertNotIn('private',text)
        restored,summary=list_sharing.validate(document,app.normalize)
        self.assertEqual([r['type'] for r in restored['items']],['episode','movie'])
        self.assertEqual(restored['items'][0]['show_tmdb'],'2');self.assertEqual(restored['items'][0]['episode'],'1')
        self.assertTrue(all(r['status']=='unchecked' for r in restored['items']));self.assertIsNone(restored['source'])
        self.assertNotEqual(restored['items'][0]['id'],'private1');self.assertEqual(summary['types']['episode'],1)

    def test_shared_list_validation_rejects_bad_version_scope_and_image(self):
        document=list_sharing.export({'name':'List','items':[{'type':'movie','title':'Film','tmdb':'1'}]})
        changed=copy.deepcopy(document);changed['version']=2
        with self.assertRaises(ValueError):list_sharing.validate(changed,app.normalize)
        changed=copy.deepcopy(document);changed['list']['items'][0]['type']='episode'
        with self.assertRaises(ValueError):list_sharing.validate(changed,app.normalize)
        changed=copy.deepcopy(document);changed['list']['poster']='data:image/svg+xml;base64,AAAA'
        with self.assertRaises(ValueError):list_sharing.validate(changed,app.normalize)
        changed=copy.deepcopy(document);changed['list']['items'][0]['title']={'url':'bad'}
        with self.assertRaises(ValueError):list_sharing.validate(changed,app.normalize)
        self.assertNotEqual(list_sharing.digest(document),list_sharing.digest(changed))

    def test_conservative_release_title_parsing_and_unique_match(self):
        self.assertEqual(ix.release_title({'title':'Blade.Runner.2049.2017.2160p.WEB-DL','categories':[{'id':2000}]}),('movie','Blade Runner 2049','2017'))
        self.assertEqual(ix.release_title({'title':'Some.Show.2022.S02E04.1080p','categories':[{'id':5000}]}),('show','Some Show','2022'))
        self.assertIsNone(ix.release_title({'title':'Film.Without.A.Year.1080p','categories':[{'id':2000}]}))
        movie={'id':1,'title':'Film','release_date':'2020-01-01'}
        record={'title':'Film.2020.1080p','categories':[{'id':2000}]}
        with patch('providers.cached_tmdb',return_value={'results':[movie]}):self.assertEqual(ix.resolve_search(record,{}),('movie',1))
        with patch('providers.cached_tmdb',return_value={'results':[movie,dict(movie,id=2)]}):self.assertIsNone(ix.resolve_search(record,{}))
        with patch('providers.cached_tmdb',return_value={'results':[dict(movie,title='Similar Film')]}):self.assertIsNone(ix.resolve_search(record,{}))
        mixed=dict(record,categories=[{'id':2000},{'id':5000}])
        with patch('providers.cached_tmdb',return_value={'results':[dict(movie,media_type='movie'),{'id':2,'name':'Film','media_type':'tv','first_air_date':'2020-02-01'}]}):self.assertIsNone(ix.resolve_search(mixed,{}))

    def test_fallback_maps_seeded_releases_without_provider_ids(self):
        ix._cache.clear()
        records=[{'title':'Film.2020.1080p','seeders':50,'categories':[{'id':2000}]},{'title':'Film.2020.2160p','seeders':100,'categories':[{'id':2000}]}]
        movie={'id':1,'title':'Film','release_date':'2020-01-01','vote_count':1000,'vote_average':8}
        def metadata(path,settings):return {'results':[movie]} if path.startswith('search/') else movie
        with patch('providers.cached_tmdb',side_effect=metadata):
            rows,warnings=ix.candidates({'prowlarr':{'url':'http://prowlarr','key':'key'},'tmdb':{'key':'test'}},lambda *a,**kw:records)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['seeders'],100);self.assertIn('exact title',rows[0]['matched_by'])


class SharingApiTests(unittest.TestCase):
    def test_preview_required_import_creates_unchecked_copy_without_remote_writes(self):
        import tempfile,threading,json,urllib.request,urllib.error
        from pathlib import Path
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder,patch.object(app,'DATA',Path(folder)):
            app.save_state({'settings':{},'lists':[{'id':'original','name':'Local','items':[{'id':'old','type':'movie','title':'Film','tmdb':'1','status':'available','plex_key':'private'}]}]})
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(action,body):
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/lists/share/'+action,data=json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION})
                with urllib.request.urlopen(request) as response:return json.load(response)
            try:
                with patch.object(app,'compare') as compare,patch.object(app,'request_item') as download:
                    document=post('export',{'list_id':'original'})
                    preview=post('preview',{'document':document})
                    self.assertEqual(len(app.read_state()['lists']),1)
                    with self.assertRaises(urllib.error.HTTPError) as rejected:post('import',{'document':document,'fingerprint':'wrong'})
                    rejected.exception.close()
                    imported=post('import',{'document':document,'fingerprint':preview['fingerprint']})['entry']
                    self.assertEqual(imported['items'][0]['status'],'unchecked');self.assertNotIn('plex_key',imported['items'][0]);self.assertNotEqual(imported['id'],'original')
                    self.assertEqual(len(app.read_state()['lists']),2);compare.assert_not_called();download.assert_not_called()
            finally:server.shutdown();server.server_close();thread.join()
