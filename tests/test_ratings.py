import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import app
import ratings

class RatingsTests(unittest.TestCase):
    def test_defaults_all_and_validates_preferences(self):
        self.assertEqual(ratings.preferences(None),{'main':'tmdb','display':'all'})
        self.assertEqual(ratings.preferences({'main':'imdb','display':['imdb']})['display'],['imdb'])
        for value in ({'main':'bogus'},{'display':[]},{'display':'one'}):
            with self.assertRaises(ValueError):ratings.preferences(value)

    def test_native_scales_aliases_missing_and_invalid_scores(self):
        parsed=ratings.parse({'ratings':[{'source':'imdb','value':8.2,'votes':1000},{'source':'tomatoes','value':91},{'source':'tomatoesaudience','value':87},{'source':'letterboxd','value':4.1},{'source':'tmdb','value':76},{'source':'trakt','value':81},{'source':'metacritic','value':'N/A'},{'source':'myanimelist','value':'NaN'},{'source':'rogerebert','value':99}]})
        values={r['source']:r for r in parsed}
        self.assertEqual(values['tmdb']['value'],7.6)
        self.assertEqual(values['trakt']['value'],8.1)
        self.assertEqual(values['popcorn']['value'],87)
        self.assertEqual(values['letterboxd']['maximum'],5)
        self.assertAlmostEqual(values['letterboxd']['score'],8.2)
        self.assertNotIn('metacritic',values)
        self.assertNotIn('myanimelist',values)
        self.assertNotIn('rogerebert',values)

    def test_no_parent_rating_for_episodes_or_seasons(self):
        with patch('ratings.request') as network:
            for kind in ('season','episode'):
                self.assertEqual(ratings.lookup({'type':kind,'tmdb':'1','show_tmdb':'2'},{'mdblist':{'key':'secret'}})['ratings'],[])
            network.assert_not_called()

    def test_cache_and_exact_id_validation(self):
        with tempfile.TemporaryDirectory() as folder,patch('providers.CACHE',Path(folder)):
            cfg={'mdblist':{'key':'secret'}}
            with patch('ratings.request',return_value={'ids':{'tmdb':42},'ratings':[{'source':'imdb','value':8}]}) as network:
                first=ratings.lookup({'type':'movie','tmdb':'42'},cfg)
                self.assertEqual(ratings.lookup({'type':'movie','tmdb':'42'},cfg),first)
                self.assertEqual(network.call_count,1)
            self.assertNotIn('secret',' '.join(str(p) for p in Path(folder).rglob('*')))
            with patch('ratings.request',return_value={'ids':{'tmdb':99}}):
                with self.assertRaises(ValueError):ratings.lookup({'type':'movie','tmdb':'43'},cfg)

    def test_requests_reject_untrusted_paths_without_exposing_key(self):
        with self.assertRaises(ValueError):ratings.request('https://other.test',{'mdblist':{'key':'secret'}})
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=urllib.error.HTTPError('https://api.mdblist.com?apikey=secret',401,'Unauthorized',{},None)
            with self.assertRaises(ValueError) as error:ratings.request('user',{'mdblist':{'key':'secret'}})
            self.assertNotIn('secret',str(error.exception))

    def test_preferences_and_ratings_http_and_key_redaction(self):
        with tempfile.TemporaryDirectory(dir=app.ROOT) as folder,patch.object(app,'DATA',Path(folder)):
            app.save_state({'settings':{'mdblist':{'key':'hidden-secret'}},'lists':[]})
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(path,body):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/'+path,data=json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','X-ReelCheck-Token':app.SESSION})
                with urllib.request.urlopen(req) as response:return json.load(response)
            try:
                self.assertEqual(post('ratings/preferences',{'main':'imdb','display':'all'})['display'],'all')
                self.assertEqual(app.read_state()['rating_preferences']['main'],'imdb')
                public=app.public_state(app.read_state())
                self.assertTrue(public['settings']['mdblist']['configured'])
                self.assertNotIn('hidden-secret',json.dumps(public))
                with patch('ratings.lookup',return_value={'ratings':[{'source':'imdb','value':8,'maximum':10}]}) as lookup:
                    result=post('ratings',{'items':[{'key':'movie:1','type':'movie','tmdb':'1'}]})
                    self.assertEqual(result['items'][0]['key'],'movie:1')
                    self.assertEqual(lookup.call_count,1)
            finally:
                server.shutdown();server.server_close();thread.join()
