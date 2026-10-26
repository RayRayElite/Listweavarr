import unittest
from unittest.mock import patch
import providers


class ImportOptionsTests(unittest.TestCase):
    def test_title_order_groups_seasons_numerically(self):
        rows=[{'type':'season','title':'Season 10','show_title':'Arrow','season':'10'}, {'type':'movie','title':'Batman'}, {'type':'season','title':'Season 2','show_title':'Arrow','season':'2'}]
        result=providers.arrange_import(rows,{'order':'title_asc'})
        self.assertEqual([r.get('season') for r in result],['2','10',None])
        reverse=providers.arrange_import(rows,{'order':'title_desc'})
        self.assertEqual([r.get('season') for r in reverse],[None,'2','10'])
        self.assertEqual(providers.arrange_import(rows,{}),rows)

    def test_combine_seasons_by_id_keep_episodes_and_movies(self):
        rows=[{'type':'season','title':'S2','show_title':'Arrow','show_tmdb':'1','season':'2'}, {'type':'season','title':'S1','show_title':'Arrow','show_tmdb':'1','season':'1'}, {'type':'movie','title':'Arrow','tmdb':'1'}, {'type':'episode','title':'Pilot','show_title':'Arrow','show_tmdb':'1','season':'1','episode':'1'}]
        result=providers.arrange_import(rows,{'seasons':'shows'})
        self.assertEqual([r['type'] for r in result],['show','movie','episode'])
        self.assertEqual(result[0]['tmdb'],'1');self.assertNotIn('season',result[0])
        self.assertEqual(rows[0]['type'],'season')
        with self.assertRaises(ValueError):providers.arrange_import([{'type':'season','title':'S1'}],{'seasons':'shows'})

    def test_year_unknown_last_and_invalid_options(self):
        rows=[{'type':'movie','title':'Unknown'}, {'type':'movie','title':'Old','year':'1990'}, {'type':'movie','title':'New','year':'2020'}]
        self.assertEqual([r['title'] for r in providers.arrange_import(rows,{'order':'year_desc'})],['New','Old','Unknown'])
        with self.assertRaises(ValueError):providers.import_options({'order':'invalid'})

    def test_app_trakt_link_supported(self):
        url='https://app.trakt.tv/users/maggiefan/lists/dc-in-order?sort_by=title&sort_how=desc'
        with patch.object(providers,'trakt',return_value={'items':[]}) as adapter:
            providers.import_url(url)
        adapter.assert_called_once()
