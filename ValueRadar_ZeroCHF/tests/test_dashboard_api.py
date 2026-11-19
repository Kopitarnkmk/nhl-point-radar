import unittest
from datetime import datetime, timezone, timedelta
from dashboard_api import build_dashboard, to_match

NOW=datetime(2026,11,19,0,0,tzinfo=timezone.utc)


def fixture(sport):
    start=(NOW+timedelta(hours=5)).isoformat()
    update=NOW.isoformat()
    return {'sport_key':sport, 'generated_at':update, 'fixtures':[
        {'id':'game-'+sport,'sport_key':sport,'home_team':'Team H','away_team':'Team A',
         'commence_time':start,'in_play':False,'bookmakers':[
         {'key':'pinnacle','kind':'sportsbook','title':'Pinnacle','last_update':update,'markets':{'h2h':[{'name':'Team H','price':-110},{'name':'Team A','price':100}]}},
         {'key':'classic','kind':'sportsbook','title':'Book A','last_update':update,'markets':{'h2h':[{'name':'Team H','price':125},{'name':'Team A','price':-125}]}},
         {'key':'betfair','kind':'exchange','title':'Betfair','last_update':update,'markets':{'h2h':[{'name':'Team H','price':175},{'name':'Team A','price':-150}]}}
       ]}]}


class DashboardTests(unittest.TestCase):
    def test_build_three_sports(self):
        payload=build_dashboard(fetch=fixture,now=NOW)
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['stats']['games'],3)
        self.assertEqual(len(payload['sports']),3)
        self.assertEqual(payload['stats']['bookmakers_observed'],6)
        self.assertGreaterEqual(len(payload['signals']),1)
        self.assertTrue(all(s['edge']>=7 for s in payload['signals']))

    def test_future_only(self):
        row=fixture('soccer')['fixtures'][0]
        row['in_play']=True
        self.assertIsNone(to_match(row,NOW))
        row['in_play']=False
        row['commence_time']=(NOW-timedelta(minutes=2)).isoformat()
        self.assertIsNone(to_match(row,NOW))

    def test_missing_bookmakers_no_fake_match(self):
        row=fixture('soccer')['fixtures'][0]
        row['bookmakers']=[]
        self.assertIsNone(to_match(row,NOW))

    def test_partial_error_reported(self):
        def fetch(sport):
            if sport=='nba':raise RuntimeError('Unavailable')
            return fixture(sport)
        result=build_dashboard(fetch=fetch,now=NOW)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(len(result['warnings']),1)
        self.assertTrue(result['ok'])

    def test_all_failed_returns_not_ok(self):
        def fetch(sport):raise RuntimeError('Unavailable')
        result=build_dashboard(fetch=fetch,now=NOW)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stats']['games'],0)

if __name__=='__main__':unittest.main()