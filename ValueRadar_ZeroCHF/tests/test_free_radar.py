from datetime import datetime, timezone, timedelta
import unittest
from free_radar import (parse_drops, compare_odds, can_alert, slug, sharp_probabilities, format_value)

NOW = datetime(2026,11,19,12,0,0,tzinfo=timezone.utc)
T = lambda minutes: (NOW + timedelta(minutes=minutes)).isoformat()

class FreeRadarTests(unittest.TestCase):
    def test_drop_and_ignores_future_or_stale(self):
        d = dict(eventId=42,home='A',away='B',market='moneyline',outcome='home',
                 **{'from':2.10,'to':1.88,'dropPct':10.5,'movedAt':T(-3)})
        found = parse_drops({'drops':[d]},now=NOW)
        self.assertEqual(len(found),1)
        self.assertAlmostEqual(found[0]['drop_pct'],10.5)
        d['movedAt']=T(-23)
        self.assertEqual(parse_drops({'drops':[d]},now=NOW),[])

    def test_sharp_prob_two_way(self):
        fair=sharp_probabilities({'key':'h2h','outcomes':[{'name':'A','price':1.91}, {'name':'B','price':1.91}]})
        self.assertAlmostEqual(fair[(('h2h',None),('a',None))],.5)

    def test_sharp_threeway(self):
        fair=sharp_probabilities({'key':'h2h','outcomes':[
            {'name':'A','price':2.5},{'name':'Draw','price':3.2},{'name':'B','price':3.0}]})
        self.assertEqual(len(fair),3)
        self.assertAlmostEqual(sum(fair.values()),1)

    def test_compare_identical_markets_fresh(self):
        mksharp={'key':'h2h','last_update':T(-2),'outcomes':[{'name':'A','price':1.91},{'name':'B','price':1.91}]}
        mksoft={'key':'h2h','last_update':T(-2),'outcomes':[{'name':'A','price':2.25},{'name':'B','price':1.7}]}
        fixture={'id':'id1','home_team':'A','away_team':'B','sport_key':'nba',
                 'commence_time':T(90),'is_live':False,'bookmakers':[
                 {'key':'pinnacle','markets':[mksharp],'last_update':T(-2)},
                 {'key':'bet365','title':'bet365','markets':[mksoft],'last_update':T(-2)}]}
        result=compare_odds([fixture],min_edge=5,now=NOW)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['bookmaker'],'bet365')
        self.assertAlmostEqual(result[0]['edge'],12.5)
        # pas d'alerte si l'une des cotes est périmée
        mksoft['last_update']=T(-35)
        self.assertEqual(compare_odds([fixture],now=NOW),[])
        mksoft['last_update']=T(-2)
        # ne pas comparer un résultat de match avec un handicap
        mksoft['key']='spreads'
        self.assertEqual(compare_odds([fixture],now=NOW),[])

    def test_no_unverified_book_with_missing_age(self):
        f={'id':'x','home_team':'A','away_team':'B','commence_time':T(90),'bookmakers':[
            {'key':'pinnacle','markets':[{'key':'h2h','last_update':None,'outcomes':[
               {'name':'A','price':2},{'name':'B','price':2}]}]},
            {'key':'bet365','markets':[{'key':'h2h','last_update':T(-1),'outcomes':[
               {'name':'A','price':2.5},{'name':'B','price':1.7}]}]}]}
        self.assertEqual(compare_odds([f],now=NOW),[])

    def test_wrong_spread_line_never_compared(self):
        sharp={'key':'spreads','last_update':T(-2),'outcomes':[
           {'name':'A','price':1.91,'point':-3.5},{'name':'B','price':1.91,'point':3.5}]}
        soft={'key':'spreads','last_update':T(-2),'outcomes':[
           {'name':'A','price':2.5,'point':-4.5},{'name':'B','price':1.7,'point':4.5}]}
        f={'id':'x','home_team':'A','away_team':'B','commence_time':T(60),
           'bookmakers':[{'key':'pinnacle','last_update':T(-2),'markets':[sharp]},
                         {'key':'bet365','last_update':T(-2),'markets':[soft]}]}
        self.assertEqual(compare_odds([f],now=NOW),[])

    def test_no_duplicates(self):
        state={'a':T(-12),'b':T(-120)}
        self.assertFalse(can_alert(state,'a',now=NOW,cooldown_minutes=90))
        self.assertTrue(can_alert(state,'b',now=NOW,cooldown_minutes=90))

    def test_no_stake_language(self):
        s=format_value({'home':'A','away':'B','bookmaker':'test','offered':2.1,'fair':1.8,
                        'market':'h2h','selection':'A','line':None,'edge':12})
        self.assertIn('Vérifier manuellement',s)

if __name__ == '__main__': unittest.main()
