import datetime
import unittest
from unittest.mock import patch
import poster_overlays as overlays

class PosterOverlayTests(unittest.TestCase):
    def test_terminal_status_and_network_art(self):
        for raw, expected in [('Ended','ended'),('Canceled','cancelled')]:
            with patch('providers.cached_tmdb', return_value={'status':raw,'networks':[{'name':'ABC'}]}):
                result=overlays.show_info('1403',{})
                self.assertEqual(result['status'],expected)
                self.assertEqual(result['network_asset'],'ABC.png')

    def test_airing_and_between_seasons(self):
        for date,expected in [(datetime.date.today().isoformat(),'airing'),('2001-01-01','returning')]:
            with patch('providers.cached_tmdb',return_value={'status':'Returning Series','last_episode_to_air':{'air_date':date}}):
                self.assertEqual(overlays.show_info('1',{})['status'],expected)

    def test_unknown_not_invented_and_asset_paths_are_constrained(self):
        with patch('providers.cached_tmdb',return_value={'networks':[{'name':'Unknown network'}]}):
            result=overlays.show_info('1',{})
            self.assertIsNone(result['status'])
            self.assertIsNone(result['network_asset'])
        self.assertIsNone(overlays.asset_path('/poster-overlays/../app.py'))
        self.assertIsNone(overlays.asset_path('/poster-overlays/status-top-left/..\\airing.png'))
        self.assertTrue(overlays.asset_path('/poster-overlays/status-top-left/airing.png').is_file())
