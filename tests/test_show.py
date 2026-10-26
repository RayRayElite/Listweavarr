import unittest
from unittest.mock import patch

import app
import providers


class ParentShowTests(unittest.TestCase):
    def test_tvdb_parent_resolves_without_losing_episode_scope(self):
        row = {'type':'episode', 'title':'Pilot', 'show_tvdb':'263365', 'season':'1', 'episode':'1'}
        with patch('providers.tmdb', return_value={'tv_results':[{'id':1403,'name':'Agents of S.H.I.E.L.D.'}]}):
            resolved=providers.enrich(row, {'tmdb':{'key':'secret'}})
        self.assertEqual(resolved['show_tmdb'],'1403')
        self.assertEqual((resolved['type'],resolved['season'],resolved['episode']),('episode','1','1'))

    def test_episode_id_is_never_used_as_parent_show_id(self):
        row={'type':'episode','title':'Pilot','tmdb':'999','show_tmdb':'1403','show_tvdb':'263365','season':'1','episode':'1'}
        show=providers.parent_show(row, {'tmdb':{'key':'secret'}})
        self.assertEqual(show['tmdb'],'1403')
        self.assertEqual(show['type'],'show')

    def test_full_show_coverage_marks_plex_presence_and_future_episodes(self):
        show={'type':'show','title':'Example','tmdb':'10','tvdb':'20'}
        catalog=[{'type':'show','title':'Example','ids':{'tmdb':'10','tvdb':'20'},'key':'30','library':'TV'}]
        raw={'seasons':[{'season_number':1,'name':'Season 1'}]}
        season={'episodes':[{'episode_number':1,'name':'First','air_date':'2000-01-01'},{'episode_number':2,'name':'Second','air_date':'2000-01-02'},{'episode_number':3,'name':'Future','air_date':'2999-01-01'}]}
        with patch('providers.parent_show',return_value=show),patch('providers.title_details',return_value={'title':'Example'}),patch('app.plex_catalog',return_value=catalog),patch('app.plex_leaves',return_value=[{'season':'1','episode':'1','key':'40'}]),patch('providers.cached_tmdb',side_effect=[raw,season]):
            result=app.show_overview({'type':'episode'}, {'plex':{'url':'http://nas'}})
        self.assertEqual(result['available'],1)
        self.assertEqual(result['missing'],1)
        self.assertEqual([e['status'] for e in result['seasons'][0]['episodes']],['available','missing','upcoming'])


class ShowRequestTests(unittest.TestCase):
    def setUp(self):
        self.overview={'show':{'type':'show','title':'Example','tmdb':'10','tvdb':'20'},'coverage_known':True,'seasons':[
            {'number':0,'episodes':[{'season':0,'episode':1,'status':'missing'}]},
            {'number':1,'episodes':[{'season':1,'episode':1,'status':'available'},{'season':1,'episode':2,'status':'missing'},{'season':1,'episode':3,'status':'upcoming'}]},
            {'number':2,'episodes':[{'season':2,'episode':1,'status':'missing'}]}]}

    def test_whole_show_request_excludes_plex_files_future_and_specials(self):
        with patch('app.show_overview',return_value=self.overview),patch('app.request_item',return_value='Requested') as request:
            app.request_show_scope({'type':'episode'}, {}, {'scope':'show','profile':1,'root':'/tv'})
        self.assertEqual(request.call_args.kwargs['allowed_episodes'],{('1','2'),('2','1')})
        self.assertEqual(request.call_args.args[0]['type'],'show')

    def test_season_request_cannot_expand_to_other_seasons(self):
        with patch('app.show_overview',return_value=self.overview),patch('app.request_item',return_value='Requested') as request:
            app.request_show_scope({'type':'episode'}, {}, {'scope':'season','season':1,'profile':1,'root':'/tv'})
        self.assertEqual(request.call_args.kwargs['allowed_episodes'],{('1','2')})
        self.assertEqual(request.call_args.args[0]['show_tvdb'],'20')

    def test_unconfirmed_coverage_prevents_any_request(self):
        self.overview['coverage_known']=False
        with patch('app.show_overview',return_value=self.overview),patch('app.request_item') as request,self.assertRaises(ValueError):
            app.request_show_scope({'type':'episode'}, {}, {'scope':'show'})
        request.assert_not_called()

    def test_core_sonarr_search_respects_allowed_coordinates(self):
        def call(settings,service,path,payload=None,method=None):
            return {'qualityprofile':[{'id':1}],'rootfolder':[{'path':'/tv'}],'series':[{'id':7,'tvdbId':20}],'episode?seriesId=7':[{'id':1,'seasonNumber':1,'episodeNumber':1,'hasFile':False},{'id':2,'seasonNumber':1,'episodeNumber':2,'hasFile':False},{'id':3,'seasonNumber':2,'episodeNumber':1,'hasFile':False}]}.get(path,{})
        with patch('app.arr_call',side_effect=call) as request:
            app.request_item({'type':'show','title':'Example','tvdb':'20'}, {},1,'/tv',allowed_episodes={('1','2')})
        command=next(c.args[3] for c in request.call_args_list if c.args[2]=='command')
        self.assertEqual(command['episodeIds'],[2])


if __name__=='__main__':
    unittest.main()
