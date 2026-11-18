from datetime import datetime, timedelta, timezone
import unittest
from public_board import american_to_decimal, board_to_fixture, scan_all, signal_tag

NOW = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)
iso = lambda minutes: (NOW + timedelta(minutes=minutes)).isoformat()


def fixture_payload(*, active=False, update=-2):
    return {'sport_key':'nhl','fixtures':[{
        'id':'nhl:abc', 'sport_key':'nhl','commence_time':iso(90),
        'home_team':'Home','away_team':'Away','in_play':active,
        'bookmakers':[
            {'kind':'sportsbook','key':'pinnacle','title':'Pinnacle','last_update':iso(update),
             'markets':{'h2h':[{'name':'Home','price':-110},{'name':'Away','price':-110}]}},
            {'kind':'sportsbook','key':'bet365','title':'bet365','last_update':iso(update),
             'markets':{'h2h':[{'name':'Home','price':+130},{'name':'Away','price':-120}]}}
        ]}]}

class TestPublicBoard(unittest.TestCase):
    def test_us_to_decimal(self):
        self.assertEqual(american_to_decimal(-100),2.0)
        self.assertEqual(american_to_decimal(100),2.0)
        self.assertEqual(american_to_decimal(150),2.5)
        self.assertAlmostEqual(american_to_decimal(-200),1.5)
        self.assertIsNone(american_to_decimal('bad'))

    def test_normalization(self):
        out = board_to_fixture(fixture_payload())
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['bookmakers'][0]['markets'][0]['outcomes'][0]['name'],'Home')
        self.assertAlmostEqual(out[0]['bookmakers'][1]['markets'][0]['outcomes'][0]['price'],2.3)

    def test_live_ignored(self):
        self.assertEqual(board_to_fixture(fixture_payload(active=True)),[])

    def test_scan_3_sports(self):
        d = fixture_payload()
        found, errors = scan_all(fetch=lambda url:d, now=NOW)
        self.assertEqual(errors,[])
        self.assertTrue(found)
        self.assertGreater(found[0]['edge'], 7)
        self.assertEqual(found[0]['market'],'h2h')

    def test_stale_odds_ignored(self):
        d = fixture_payload(update=-30)
        found, _ = scan_all(fetch=lambda url:d, now=NOW)
        self.assertFalse(found)

    def test_exchange_excluded(self):
        d = fixture_payload()
        d['fixtures'][0]['bookmakers'][1]['kind'] = 'exchange'
        found, errors = scan_all(fetch=lambda url: d, now=NOW)
        self.assertEqual(found, [])
        self.assertEqual(errors, [])

    def test_deterministic_id(self):
        c={'uid':'abc','starts_at':iso(90)}
        self.assertEqual(signal_tag(c),signal_tag(c))
        self.assertNotEqual(signal_tag(c),signal_tag({'uid':'abc','starts_at':iso(120)}))

if __name__=='__main__': unittest.main()
