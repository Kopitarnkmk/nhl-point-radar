"""Live OddsLink public-board data for ValueRadar's free web dashboard.

No credentials, no paid API, and no automatic betting. The public board may
cover only a limited window; missing market data must never be filled by guesses.
"""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
from urllib import request, error
import json

from free_radar import compare_odds, time_parse
from public_board import SPORTS, PUBLIC_BASE, board_to_fixture

SPORT_INFO = {
    'soccer': {'label': 'Football', 'icon': '⚽'},
    'nba': {'label': 'NBA', 'icon': '🏀'},
    'nhl': {'label': 'NHL', 'icon': '🏒'},
}
BOOK_EXCLUDE = {'polymarket', 'kalshi', 'novig', 'sx.bet', 'betfair', 'matchbook', '4casters'}


def request_board(sport, timeout=13):
    if sport not in SPORTS:
        raise ValueError('Sport non reconnu')
    req = request.Request(f'{PUBLIC_BASE}/{sport}',headers={
        'User-Agent':'ValueRadarWeb/1.0', 'Accept':'application/json'})
    with request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError('Service source indisponible')
        data = json.loads(response.read(6_000_000).decode('utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('fixtures'), list):
        raise ValueError('Format de données inattendu')
    return data


def date_iso(v):
    t = time_parse(v)
    return t.isoformat() if t else None


def fmt_market(m):
    return {'h2h':'Résultat du match','spreads':'Handicap','totals':'Total de points/buts'}.get(m, str(m))


def to_match(f, now):
    """Convert a public fixture without confusing snapshot freshness and live status."""
    if f.get('in_play'):
        return None
    start = time_parse(f.get('commence_time'))
    if not start or start <= now:
        return None
    sport = f.get('sport_key', '')
    books = [b for b in f.get('bookmakers', []) if isinstance(b,dict)
             and b.get('kind')=='sportsbook' and str(b.get('key','')).lower() not in BOOK_EXCLUDE]
    if not books:
        return None
    market_types = set()
    best = None
    pinnacle = next((b for b in books if str(b.get('key','')).lower()=='pinnacle'),None)
    for book in books:
        for k, outs in (book.get('markets') or {}).items():
            if k in ('h2h','spreads','totals') and isinstance(outs,list):
                market_types.add(k)
    if pinnacle:
        # Report Pinnacle's latest known h2h price for either side as a reference.
        for o in (pinnacle.get('markets') or {}).get('h2h', []) or []:
            from public_board import american_to_decimal
            val = american_to_decimal(o.get('price')) if isinstance(o,dict) else None
            if val and val > 1:
                best = val
                break
    return {'id':str(f.get('id') or ''),'sport':sport,'sport_label':SPORT_INFO.get(sport,{}).get('label',sport),
            'home':str(f.get('home_team') or ''),'away':str(f.get('away_team') or ''),
            'starts_at':start.isoformat(),'books_count':len(books),
            'market_types':[fmt_market(x) for x in ('h2h','spreads','totals') if x in market_types],
            'has_pinnacle':bool(pinnacle),'pinnacle_sample':best,
            'league':str((f.get('league') or {}).get('title','') if isinstance(f.get('league'),dict) else (f.get('league_title') or '')),
            'source':'OddsLink — tableau public'}


def build_dashboard(*, fetch=request_board, now=None):
    now = now or datetime.now(timezone.utc)
    all_games, signals, watch, sport_stats, errors = [], [], [], [], []
    source_times=[]
    def get(sport):
        return fetch(sport)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(get, s):s for s in SPORTS}
        for future, sport in futures.items():
            try:
                data=future.result(timeout=25)
                t=date_iso(data.get('generated_at'))
                if t: source_times.append(t)
                games=[v for f in data.get('fixtures',[]) if (v:=to_match(f,now))]
                all_games.extend(games)
                # Do not treat exchange/prediction venues as classical sportsbooks,
                # even if a provider accidentally labels one as such.
                safe = dict(data)
                safe['fixtures'] = [dict(f, bookmakers=[b for b in f.get('bookmakers', [])
                    if isinstance(b,dict) and b.get('kind')=='sportsbook'
                    and str(b.get('key','')).lower() not in BOOK_EXCLUDE])
                    for f in data.get('fixtures', []) if isinstance(f,dict)]
                normalized=board_to_fixture(safe)
                candidates=compare_odds(normalized, now=now,min_edge=0,
                                        max_age_minutes=15,max_results=100)
                # Deduplicate by event/market/selection/line, keep the highest edge
                unique={}
                for c in candidates:
                    k=(c.get('sport'),c.get('home'),c.get('away'),c.get('market'),c.get('selection'),c.get('line'),c.get('starts_at'))
                    if k not in unique or c.get('edge',0)>unique[k]['edge']:
                        unique[k]=c
                for c in unique.values():
                    item={k:c.get(k) for k in ('uid','sport','home','away','starts_at','bookmaker','market',
                                                   'selection','line','offered','fair','edge','book_price_at','sharp_price_at','link')}
                    item['market_label']=fmt_market(c.get('market'))
                    item['book_price_at']=date_iso(item['book_price_at'])
                    item['sharp_price_at']=date_iso(item['sharp_price_at'])
                    item['edge']=round(float(item['edge']),2)
                    if item['edge']>=7:
                        item['grade']='potential'; signals.append(item)
                    elif item['edge']>=2:
                        item['grade']='watch';watch.append(item)
                sport_stats.append({'sport':sport,'name':SPORT_INFO[sport]['label'],
                                    'games':len(games),'source_fixtures':len(data['fixtures']),
                                    'status':'ok'})
            except Exception as exc:
                # No fabricated scores or silently valid "live" state.
                errors.append(f'{SPORT_INFO[sport]["label"]} : {type(exc).__name__}')
                sport_stats.append({'sport':sport,'name':SPORT_INFO[sport]['label'],
                                    'games':0,'source_fixtures':0,'status':'error'})
    all_games.sort(key=lambda g:g['starts_at'])
    signals.sort(key=lambda x:-x['edge'])
    watch.sort(key=lambda x:-x['edge'])
    total_books=sum(g['books_count'] for g in all_games)
    generated=max(source_times) if source_times else None
    return {'ok':len(errors)<len(SPORTS),'status':'partial' if errors else 'ok',
            'scanned_at':now.isoformat(),'source_at':generated,'sports':sport_stats,
            'games':all_games,'signals':signals,'watch':watch[:20],
            'stats':{'games':len(all_games),'signals':len(signals),'watch':len(watch),
                     'bookmakers_observed':total_books},
            'parameters':{'min_edge':7,'watch_edge':2,'max_age_minutes':15,'scan_schedule_minutes':30},
            'source':'OddsLink public board — fenêtre limitée, aucun accès JouezSport vérifié',
            'alerts_url':'https://github.com/Kopitarnkmk/nhl-point-radar/issues/1',
            'warnings':errors, 'limitations':['Uniquement cotes pré-match exposées par le tableau public',
                    'La comparaison ne prouve pas que la cote est disponible en Suisse',
                    'Aucun historique de baisses Pinnacle sans flux dédié']}