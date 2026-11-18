#!/usr/bin/env python3
"""ValueRadar gratuit: signaux pré-match (PinnFeed + OddsLink), Telegram.

Aucun ordre, aucune API payante, aucun paiement. Dépendances: bibliothèque standard.
Pour fonctionner en continu, exécuter avec GitHub Actions sur dépôt public.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PFD = 'https://pinnfeed.io/v1/drops'
OL_BASE = 'https://oddslink.app/v1/sports'
TG_BASE = 'https://api.telegram.org'
DEFAULT_SPORTS = ('soccer', 'nba', 'nhl')


def now_utc():
    return datetime.now(timezone.utc)


def time_parse(x):
    if x is None or x == '': return None
    try:
        if isinstance(x, (int, float)):
            return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, tz=timezone.utc)
        dt = datetime.fromisoformat(str(x).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def float_ok(x):
    try:
        val = float(x)
        return val if val > 0 and val < 10000 else None
    except (TypeError, ValueError):
        return None


def slug(x):
    import unicodedata
    x = unicodedata.normalize('NFKD', str(x or '')).encode('ascii', errors='ignore').decode('ascii').lower()
    return re.sub('[^a-z0-9]+', '', x)


def http_json(url, *, token='', header='X-API-Key', method='GET', data=None):
    if not url.startswith('https://'): raise ValueError('HTTPS obligatoire')
    headers = {'User-Agent': 'ValueRadarFree/2.0', 'Accept': 'application/json'}
    if token: headers[header] = token
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=65) as resp:
        result = json.loads(resp.read(7_000_000).decode('utf-8'))
        if not isinstance(result, (list, dict)): raise ValueError('Réponse JSON inattendue')
        return result


def load_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    temp.replace(path)


def can_alert(state, uid, now=None, cooldown_minutes=90):
    now = now or now_utc()
    v = time_parse(state.get(uid))
    return not v or (now - v).total_seconds() >= cooldown_minutes * 60


def prune_state(state, now=None, days=10):
    now = now or now_utc()
    return {k: v for k, v in state.items() if time_parse(v) and 0 <= (now-time_parse(v)).total_seconds() < days*86400}


def tg_send(bot, chat, message):
    if not bot or not chat: return False
    if not re.match(r'^\d+:[A-Za-z0-9_-]+$', bot): raise ValueError('Token Telegram invalide')
    payload = {'chat_id': chat, 'text': message, 'disable_web_page_preview': 'true'}
    response = http_json(f'{TG_BASE}/bot{bot}/sendMessage', method='POST', data=payload)
    if not response.get('ok'):
        raise RuntimeError('Telegram a refusé la notification')
    return True


def dict_items(response, keys):
    if isinstance(response, list): return response
    for k in keys:
        if isinstance(response.get(k), list): return response[k]
    return []


def parse_drops(payload, min_pct=4, max_age_minutes=22, now=None):
    now = now or now_utc()
    out = []
    for d in dict_items(payload, ('drops', 'data', 'results', 'items')):
        if not isinstance(d, dict): continue
        if d.get('live') is True: continue
        pct = float_ok(d.get('dropPct'))
        moved = time_parse(d.get('movedAt'))
        if pct is None or pct < min_pct or moved is None: continue
        age = (now - moved).total_seconds()
        if age < -90 or age > max_age_minutes*60: continue
        sharp_from = float_ok(d.get('from'))
        sharp_to = float_ok(d.get('to'))
        if not sharp_from or not sharp_to or sharp_to >= sharp_from: continue
        starts = time_parse(d.get('startTime') or d.get('commenceTime'))
        if starts and starts <= now: continue
        name = str(d.get('outcome') or d.get('side') or '').strip()
        home = str(d.get('home') or d.get('homeTeam') or '')
        away = str(d.get('away') or d.get('awayTeam') or '')
        if not home or not away or not name: continue
        market = d.get('market') or ''
        if isinstance(market, dict): market = market.get('type') or market.get('name') or ''
        uid = 'drop:' + '|'.join(map(str,(d.get('eventId'),market,d.get('period'),d.get('line'),name)))
        out.append({'uid': uid, 'sport': d.get('sport') or '', 'home': home, 'away': away,
                    'market': str(market), 'selection': name, 'line': d.get('line'),
                    'from': sharp_from, 'to': sharp_to, 'drop_pct': round(pct,2),
                    'age_min': round(max(0, age)/60,1), 'source': 'PinnFeed (retard 30s)',
                    'kind': 'BAISSE SHARP — VÉRIFIER LA COTE', 'starts_at': starts.isoformat() if starts else ''})
    return sorted(out, key=lambda r: -r['drop_pct'])


def sharp_probabilities(market):
    """Probabilités Pinnacle sans marge, par marché et ligne STRICTEMENT identiques."""
    outcomes = market.get('outcomes') or []
    grouped = {}
    for o in outcomes:
        p = float_ok(o.get('price'))
        if not p or p <= 1: continue
        key = market_group_key(market['key'], o)
        grouped.setdefault(key, []).append(o)
    probs = {}
    for key, entries in grouped.items():
        if len({slug(e.get('name')) for e in entries}) < 2: continue
        prices = [float(e['price']) for e in entries]
        total = sum(1.0 / p for p in prices)
        if not 1.0 <= total <= 1.20: continue  # éviter marchés incomplets ou corrompus
        for o in entries:
            p = float(o['price'])
            probs[(key, outcome_key(o))] = (1/p)/total
    return probs


def market_group_key(market_key, outcome):
    point = outcome.get('point')
    if point is None: return (market_key, None)
    number = float(point)
    if market_key == 'spreads': return (market_key, round(abs(number),3))
    return (market_key, round(number,3))


def outcome_key(outcome):
    return (slug(outcome.get('name')), round(float(outcome['point']),3) if outcome.get('point') is not None else None)


def market_key(m):
    return (m.get('key'), str(m.get('period') or 'full'))


def freshness_ok(book, market, now=None, max_age_minutes=20):
    now = now or now_utc()
    t = time_parse(market.get('last_update') or book.get('last_update'))
    return t is not None and -60 <= (now-t).total_seconds() <= max_age_minutes*60


def compare_odds(payload, *, min_edge=5.0, now=None, max_age_minutes=20, max_results=30):
    """Évalue uniquement des issues strictement identiques sur le même match et la même ligne.

    Ce sont des *opportunités à vérifier*, pas des conseils de miser en Suisse.
    """
    now = now or now_utc()
    candidates = []
    for f in dict_items(payload, ('data','events','results')):
        if not isinstance(f,dict) or f.get('is_live'): continue
        start = time_parse(f.get('commence_time'))
        if start is None or start <= now: continue
        books = f.get('bookmakers') or []
        if not isinstance(books,list): continue
        sharp = next((b for b in books if str(b.get('key','')).lower() == 'pinnacle'), None)
        if not sharp: continue
        sharp_mkt = {market_key(m): m for m in sharp.get('markets',[]) if isinstance(m,dict)}
        for b in books:
            bname = b.get('title') or b.get('key') or ''
            if b is sharp or b.get('key') in ('pinnacle', 'kalshi', 'polymarket'):
                continue
            for market in b.get('markets', []):
                if not isinstance(market,dict): continue
                mk = market_key(market)
                ref = sharp_mkt.get(mk)
                if not ref: continue
                if not freshness_ok(sharp,ref,now,max_age_minutes) or not freshness_ok(b,market,now,max_age_minutes): continue
                fair = sharp_probabilities(ref)
                for outcome in market.get('outcomes',[]):
                    if not isinstance(outcome,dict): continue
                    local_price = float_ok(outcome.get('price'))
                    if not local_price or not 1.2 <= local_price <= 12: continue
                    key = (market_group_key(market.get('key'),outcome), outcome_key(outcome))
                    fair_p = fair.get(key)
                    if fair_p is None: continue
                    edge = (local_price * fair_p-1)*100
                    if not min_edge <= edge <= 25: continue
                    uid = 'value:'+ '|'.join([str(f.get('id')), str(b.get('key')),str(mk),str(outcome_key(outcome))])
                    candidates.append({
                        'uid': uid, 'kind': 'ÉCART DE COTE — VÉRIFICATION REQUISE', 'sport': f.get('sport_key'),
                        'home': f.get('home_team'), 'away': f.get('away_team'), 'starts_at': start.isoformat(),
                        'bookmaker': bname, 'market': market.get('key'),
                        'selection': outcome.get('name'), 'line': outcome.get('point'),
                        'offered': round(local_price,3), 'fair': round(1/fair_p,3),
                        'edge': round(edge,2), 'book_price_at': market.get('last_update') or b.get('last_update'),
                        'sharp_price_at': ref.get('last_update') or sharp.get('last_update'),
                        'link': b.get('link') or '', 'source': 'OddsLink (pré-match)',
                    })
    return sorted(candidates,key=lambda r:-r['edge'])[:max_results]


def format_drop(d):
    line = (' · Ligne '+str(d['line'])) if d.get('line') is not None else ''
    return (f"📉 BAISSE PINNACLE — ALERTE DE SURVEILLANCE\n"
            f"{d['home']} – {d['away']}\n"
            f"Marché : {d['market']} · {d['selection']}{line}\n"
            f"Pinnacle : {d['from']:.2f} → {d['to']:.2f} ({d['drop_pct']:.1f}% de baisse)\n"
            f"Mouvement : il y a {d['age_min']:.0f} min\n"
            f"⛔ AUCUN SIGNAL DE MISE : cote JouezSport non vérifiée."
            f"\nVérifier la cote disponible et le marché exact avant de décider.")


def format_value(d):
    line = (' · Ligne '+str(d['line'])) if d.get('line') is not None else ''
    return (f"🔎 VALUE POTENTIELLE — VÉRIFIER\n{d['home']} – {d['away']}\n"
            f"{d['bookmaker']} : {d['offered']:.2f} · cote théorique Pinnacle : {d['fair']:.2f}\n"
            f"Marché {d['market']} : {d['selection']}{line}\n"
            f"Edge estimé : +{d['edge']:.1f}% (non garanti)\n"
            f"⛔ Bookmaker étranger : disponibilité en Suisse non confirmée. "
            f"Vérifier manuellement sur JouezSport. Aucun pari automatique.")


def main(argv=None):
    ap = argparse.ArgumentParser(description='ValueRadar gratuit sans abonnement')
    ap.add_argument('--mode', choices=['drops','compare','demo'], default='drops')
    ap.add_argument('--state',default='ValueRadar_ZeroCHF/state.json')
    ap.add_argument('--dry-run',action='store_true')
    args = ap.parse_args(argv)
    now = now_utc()
    old = prune_state(load_state(args.state),now)
    if args.mode=='demo':
        print('MODE DÉMO sans données réelles ni alertes')
        print(format_drop({'home':'Equipe A','away':'Equipe B','market':'moneyline','selection':'home', 'line':None,'from':2.1,'to':1.88,'drop_pct':10.48,'age_min':3}))
        return 0
    bot = os.getenv('TELEGRAM_BOT_TOKEN','')
    chat = os.getenv('TELEGRAM_CHAT_ID','')
    if not bot or not chat:
        print('CONFIGURATION INCOMPLÈTE : renseigner TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID (GitHub Secrets).',file=sys.stderr)
        return 2
    if args.mode=='drops':
        key = os.getenv('PINNFEED_KEY','')
        if not key:
            print('PINNFEED_KEY manquante (offre Free €0)',file=sys.stderr); return 2
        sports=os.getenv('PINNFEED_SPORTS','soccer,basketball')
        # Ne choisir que les 2 sports configurés sur le compte gratuit.
        params=urllib.parse.urlencode({'sport':sports, 'minutes':15,'min_pct':4,'limit':75,'main':'true','live':'false'})
        data=http_json(f'{PFD}?{params}',token=key,header='x-api-key')
        alerts=parse_drops(data,now=now)
    else:
        key=os.getenv('ODDSLINK_KEY','')
        if not key:
            print('ODDSLINK_KEY manquante (offre Free $0)',file=sys.stderr); return 2
        alerts=[]
        for sport in DEFAULT_SPORTS:
            url=f'{OL_BASE}/{sport}/odds?oddsFormat=decimal&markets=h2h,spreads,totals'
            try:
                raw=http_json(url,token=key)
                alerts.extend(compare_odds(raw,now=now))
            except (urllib.error.URLError, ValueError, KeyError) as exc:
                print(f'Sport {sport}: erreur {type(exc).__name__}: {exc}',file=sys.stderr)
        alerts.sort(key=lambda r:-r.get('edge',0))
    print(f'{now.isoformat()}: {args.mode} : {len(alerts)} signaux admissibles à vérifier')
    sent=0
    for d in alerts:
        uid=d['uid']
        if not can_alert(old,uid,now,cooldown_minutes=(90 if args.mode=='drops' else 720)): continue
        msg = format_drop(d) if args.mode=='drops' else format_value(d)
        if args.dry_run:
            print('\n' + msg+'\n')
        else:
            # N'enregistrer l'UID qu'après envoi confirmé.
            tg_send(bot,chat,msg)
            old[uid]=now.isoformat()
            sent+=1
            if sent>=10: break  # Protection anti-spam.
    if not args.dry_run: save_state(args.state,old)
    print(f'{sent} notifications envoyées' if not args.dry_run else 'Mode dry-run : aucun envoi')
    return 0


if __name__=='__main__':
    try: sys.exit(main())
    except (urllib.error.URLError, ValueError, RuntimeError, KeyError) as exc:
        print(f'ERREUR : {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(1)
