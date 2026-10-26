import unittest
from unittest.mock import patch
import popular_downloads as charts
import explore

class DownloadCharts(unittest.TestCase):
    def test_movie_chart_order_and_identity(self):
        html='<table><tr><td>2</td><td>1</td><td>Second</td><td><a href="https://www.imdb.com/title/tt1234567/">7</a></td></tr><tr><td>1</td><td>2</td><td>First</td><td><a href="https://www.imdb.com/title/tt7654321/">8</a></td></tr></table>'
        with patch.object(charts,'fetch',return_value=html):
            rows=charts.source_rows('downloads_movies')
        self.assertEqual([r['rank'] for r in rows],[1,2]);self.assertEqual(rows[0]['imdb'],'tt7654321')
    def test_tv_deduplicates_by_show_without_summing(self):
        import json
        feed=json.dumps({'torrents':[{'imdb_id':'1234567','seeds':12,'magnet_url':'private'},{'imdb_id':'1234567','seeds':30},{'imdb_id':'7654321','seeds':20},{'imdb_id':'0','seeds':999}]})
        with patch.object(charts,'fetch',return_value=feed):rows=charts.source_rows('downloads_tv')
        self.assertEqual([r['seeders'] for r in rows],[30,20]);self.assertNotIn('magnet_url',str(rows))
    def test_chart_bypasses_quality_language_but_respects_ignore_and_missing(self):
        details={'id':10,'title':'Example','release_date':'2020-01-01','vote_average':3,'vote_count':1,'original_language':'fr'}
        state={'settings':{'tmdb':{'key':'test'}},'explore_languages':['en']}
        catalog=[{'type':'movie','title':'Example','ids':{'tmdb':'10'}}]
        with patch.object(charts,'candidates',return_value=([{'details':details,'rank':1}],[])),patch.object(explore,'library',return_value=(catalog,True)):
            result=explore.extra_shelf(state,{'shelf':'downloads_movies'},None,None)
            self.assertTrue(result['rows'][0]['items'][0]['in_library'])
            self.assertEqual(explore.extra_shelf(state,{'shelf':'downloads_movies','missing_only':True},None,None)['rows'][0]['items'],[])
    def test_failure_is_explicit(self):
        with patch.object(charts,'_cache',{}),patch.object(charts,'fetch',side_effect=OSError()):
            with self.assertRaisesRegex(ValueError,'No chart was substituted'):charts.candidates('downloads_movies',{})

if __name__=='__main__':unittest.main()
