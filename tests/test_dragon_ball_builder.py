import unittest
from unittest.mock import patch
import text_list_builder as b

SAMPLE='''Dragon Ball Episodes 1 - 43
Plot summary that is not a title.
MOVIE: Curse of the Blood Rubies
Dragon Ball Z Episodes 1 - 35 [1 - 26 DUB]
SPECIAL: The History of Trunks
Dragon Ball Z Episodes 36 - 106 [27 - 92 DUB]
Dragon Ball Z Episodes 287 [272 DUB]
Dragon Ball: Daima (DBD Episodes 1 - 20)
MOVIE: Battle of Gods (DBS Episodes 1 - 14)
MOVIE: Resurrection F (DBS Episodes 15 - 27)
Dragon Ball Super Episodes 28 - 131
Dragon Ball GT Complete Series (Non-Canon, Optional)
OPTIONAL: Super Dragon Ball Heroes'''

class DragonBallBuilderTests(unittest.TestCase):
    def test_headings_only_and_dub_precedence(self):
        rows=b.infer(SAMPLE)
        self.assertEqual(len(rows),12)
        self.assertEqual((rows[2]['query'],rows[2]['episode'],rows[2]['episode_end']),('Dragon Ball Z','1','26'))
        self.assertEqual((rows[4]['episode'],rows[4]['episode_end']),('27','92'))
        self.assertEqual((rows[5]['episode'],rows[5]['episode_end']),('272','272'))
        self.assertEqual(rows[6]['query'],'Dragon Ball DAIMA');self.assertEqual(rows[6]['episode_end'],'20')
        self.assertEqual(rows[7]['type'],'movie');self.assertEqual(rows[7]['query'],'Battle of Gods')
        self.assertEqual(rows[-2]['type'],'show');self.assertEqual(rows[-1]['query'],'Super Dragon Ball Heroes')
        self.assertTrue(all(row.get('numbering')=='absolute' for row in rows if row['type']=='episode'))

    def test_opening_post_only_not_larger_quoted_reply(self):
        html='<title>Dragon Ball watch order</title><article><div class="bbWrapper">'+SAMPLE.replace('\n','<br>')+'</div></article><article><div class="bbWrapper">'+(SAMPLE*3).replace('\n','<br>')+'</div></article>'
        result=b.extract_html(html)
        self.assertEqual(len(b.infer(result['text'])),12)
        self.assertNotIn('Plot summary',result['text']);self.assertIn('DUB',result['notice'])

    def test_dub_is_not_silently_used_as_original_air_order(self):
        row=b.infer(SAMPLE)[2]
        with patch('providers.cached_tmdb',return_value={'seasons':[{'season_number':1,'episode_count':291}]}):
            result=b.scope_proposal(row,{'type':'show','tmdb':'1'},{})
        self.assertIn('276-episode DUB',result['scope_error'])

    def test_other_guides_keep_all_candidate_lines(self):
        self.assertEqual(len(b.infer('Example Episodes 1 - 3\nNotes to review')),2)

    def test_uncut_english_uses_original_ranges_and_maps_sagas(self):
        row=b.infer(SAMPLE,dragon_edition='original')[4]
        self.assertEqual((row['episode'],row['episode_end']),('36','106'))
        details={'seasons':[{'season_number':0,'episode_count':10}]+[{'season_number':i+1,'episode_count':n} for i,n in enumerate([39,35,33,32,26,29,25,34,38])]}
        with patch('providers.cached_tmdb',return_value=details):result=b.scope_proposal(row,{'type':'show','tmdb':'12971'},{})
        self.assertEqual(result['scope_segments'],[{'season':'1','episode':'36','episode_end':'39'},{'season':'2','episode':'1','episode_end':'35'},{'season':'3','episode':'1','episode_end':'32'}])

    def test_absolute_save_crosses_seasons_and_keeps_movie_in_place(self):
        import app
        def metadata(path,settings):
            if path=='tv/1':return {'name':'Example','seasons':[{'season_number':1,'episode_count':2},{'season_number':2,'episode_count':2}]}
            if path=='movie/2':return {'title':'Movie'}
            if '/episode/' in path:return {'id':100,'name':'Episode'}
            if '/season/' in path:return {'id':10,'episodes':[{'id':i,'episode_number':i,'name':'Episode'} for i in (1,2)]}
            raise AssertionError(path)
        rows=[{'confirmed':True,'type':'episode','tmdb':'1','season':'1','episode':'2','episode_end':'4','numbering':'absolute'},{'confirmed':True,'type':'movie','tmdb':'2'}]
        with patch('providers.cached_tmdb',side_effect=metadata):result=b.confirmed_items(rows,{},app.normalize)
        self.assertEqual([(r.get('season'),r.get('episode')) for r in result], [('1','2'),('2','1'),('2','2'),(None,None)])

    def test_incomplete_season_counts_and_out_of_bounds_fail(self):
        row={'type':'episode','season':'1','episode':'1','episode_end':'9','numbering':'absolute'}
        for seasons in ([{'season_number':1,'episode_count':4},{'season_number':2,'episode_count':4}],[{'season_number':1,'episode_count':4},{'season_number':3,'episode_count':5}]):
            with patch('providers.cached_tmdb',return_value={'seasons':seasons}):self.assertIn('scope_error',b.scope_proposal(row,{'type':'show','tmdb':'1'},{}))
