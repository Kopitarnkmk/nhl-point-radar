#!/usr/bin/env python3
"""ValueRadar : cotes publiques OddsLink, notifications via GitHub Issues.

Fonctionne sans clé de bookmaker. L'analyse est exploratoire; aucun pari.
Exécution automatisée par GitHub Actions (dépôt public).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from free_radar import compare_odds, now_utc, time_parse, tg_send

SPORTS = ('soccer', 'nba', 'nhl')
PUBLIC_BASE = 'https://oddslink.app/v1/public/board'
ISSUES_API = 'https://api.github.com'


def american_to_decimal(price):
    try:
        p = int(price)
    except (ValueError, TypeError):
        return None
    if not -50000 < p < 50000 or abs(p) < 100:
        return None
    return round(1 + (p / 100 if p > 0 else 100 / abs(p)), 6)


def board_to_fixture(board):
    """Convertit la grille publique (markets dict, prix US) en cotes décimales.

    Refuse les événements live, prix invalides et marchés incomplets. Le moteur
    compare_odds vérifie ensuite le même match/issue/ligne et la fraîcheur.
    """
    output = []
    for f in board.get('fixtures', []):
        if not isinstance(f, dict) or f.get('in_play') is True:
            continue
        books = []
        for b in f.get('bookmakers', []):
            if not isinstance(b, dict) or b.get('kind') != 'sportsbook':
                continue
            markets = []
            for mk, outcomes in (b.get('markets') or {}).items():
                if mk not in ('h2h', 'spreads', 'totals') or not isinstance(outcomes, list):
                    continue
                valid = []
                for o in outcomes:
                    if not isinstance(o, dict):
                        continue
                    p = american_to_decimal(o.get('price'))
                    if p is None or not o.get('name'):
                        continue
                    outcome = {'name': o['name'], 'price': p}
                    if o.get('point') is not None:
                        try:
                            outcome['point'] = float(o['point'])
                        except (TypeError, ValueError):
                            continue
                    valid.append(outcome)
                if len(valid) >= 2:
                    markets.append({'key': mk, 'outcomes': valid, 'last_update': b.get('last_update')})
            if markets:
                books.append({'key': b.get('key'), 'title': b.get('title'), 'last_update': b.get('last_update'),
                              'link': b.get('link'), 'markets': markets})
        output.append({'id': f.get('id'), 'sport_key': f.get('sport_key') or board.get('sport_key'),
                       'home_team': f.get('home_team'), 'away_team': f.get('away_team'),
                       'commence_time': f.get('commence_time'), 'is_live': False,
                       'bookmakers': books})
    return output


def http_json(url, *, token=None, data=None):
    if not url.startswith('https://'):
        raise ValueError('HTTPS obligatoire')
    headers = {'Accept': 'application/vnd.github+json' if 'api.github.com' in url else 'application/json',
               'User-Agent': 'ValueRadarZeroCHF/1.0'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
        headers['X-GitHub-Api-Version'] = '2022-11-28'
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=payload, headers=headers,
                                 method='POST' if payload is not None else 'GET')
    with urllib.request.urlopen(req, timeout=50) as resp:
        return json.loads(resp.read(8_000_000).decode('utf-8'))


def scan_all(fetch=http_json, *, now=None, min_edge=7.0):
    now = now or now_utc()
    results = []
    errors = []
    for sport in SPORTS:
        try:
            response = fetch(f'{PUBLIC_BASE}/{sport}')
            if 'fixtures' not in response or not isinstance(response['fixtures'], list):
                raise ValueError('Réponse sans liste de rencontres')
            candidates = compare_odds(board_to_fixture(response), now=now, min_edge=min_edge,
                                      max_age_minutes=15, max_results=15)
            for c in candidates:
                if c.get('home') and c.get('away') and c.get('bookmaker'):
                    results.append(c)
            print(f'{sport}: {len(response["fixtures"])} matchs; {len(candidates)} valeurs potentielles')
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError) as exc:
            errors.append(f'{sport}: {type(exc).__name__} {exc}')
            print(f'ERREUR {errors[-1]}',file=sys.stderr)
    # Une seule alerte par marché/sélection d'un match : garder le prix sportsbook le plus haut.
    best = {}
    for c in results:
        key = (c['sport'], c['home'], c['away'], c['market'], c['selection'], c.get('line'), c['starts_at'])
        if key not in best or c['edge'] > best[key]['edge']:
            best[key] = c
    return sorted(best.values(), key=lambda c: c['edge'], reverse=True), errors


def issue_comment_url(repo, issue):
    if not repo or not repo.count('/') == 1 or not issue or not str(issue).isdigit():
        raise ValueError('Dépôt/issue invalides')
    return f'{ISSUES_API}/repos/{repo}/issues/{issue}/comments'


def signal_tag(c):
    payload = f"{c['uid']}|{c.get('starts_at','')}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]


def existing_tags(repo, issue, token, fetch=http_json):
    if not token:
        return set()
    url = issue_comment_url(repo, issue) + '?per_page=100&sort=created&direction=desc'
    comments = fetch(url, token=token)
    if not isinstance(comments, list):
        raise ValueError('Liste de commentaires indisponible')
    import re
    result = set()
    for c in comments:
        result.update(re.findall(r'<!-- vr:([a-f0-9]{20}) -->',c.get('body') or ''))
    return result


def post_signal(repo, issue, token, c, fetch=http_json):
    msg = (f"@Kopitarnkmk 🔎 **ValueRadar : écart de cote à vérifier**\n\n"
           f"**{c['home']} – {c['away']}** · {c.get('sport','')}\n\n"
           f"- Marché : `{c['market']}` · **{c['selection']}**"
           f"{' (ligne '+str(c['line'])+')' if c.get('line') is not None else ''}\n"
           f"- Référence sans marge (Pinnacle) : **{c['fair']:.2f}**\n"
           f"- **{c['bookmaker']}** : **{c['offered']:.2f}**\n"
           f"- Écart estimé : **+{c['edge']:.1f}%** (non garanti)\n"
           f"- Coup d'envoi UTC : {c['starts_at']}\n\n"
           f"⚠️ Cotes observées sur un tableau public, à vérifier directement. "
           f"L'opérateur peut ne pas être autorisé en Suisse ; aucune cote JouezSport confirmée. "
           f"Aucun ordre de mise automatique.\n\n"
           f"<!-- vr:{signal_tag(c)} -->")
    return fetch(issue_comment_url(repo, issue), token=token, data={'body':msg})


def run(argv=None):
    parser = argparse.ArgumentParser(description='ValueRadar gratuit sans clé API')
    parser.add_argument('--test',action='store_true',help='scan réel sans notifications')
    parser.add_argument('--min-edge',type=float,default=7.0)
    args = parser.parse_args(argv)
    if not 0 < args.min_edge < 20:
        parser.error('min-edge entre 0 et 20 %')
    candidates, errors = scan_all(min_edge=args.min_edge)
    print(f'TOTAL: {len(candidates)} candidats, {len(errors)} erreur(s)')
    if args.test:
        for c in candidates[:5]:
            print(f"SCAN {c['home']} vs {c['away']} {c['bookmaker']} {c['offered']} edge {c['edge']}%")
        return 1 if len(errors) == len(SPORTS) else 0
    token = os.getenv('GITHUB_TOKEN','')
    repo = os.getenv('GITHUB_REPOSITORY','')
    issue = os.getenv('VALUE_RADAR_ISSUE','')
    if not all([token,repo,issue]):
        print('GITHUB_TOKEN, GITHUB_REPOSITORY ou VALUE_RADAR_ISSUE manquants',file=sys.stderr)
        return 2
    known = existing_tags(repo, issue, token)
    sent = 0
    for c in candidates:
        if signal_tag(c) in known:
            continue
        post_signal(repo, issue, token, c)
        known.add(signal_tag(c))
        sent += 1
        if sent >= 3:
            break
    print(f'{sent} notifications GitHub envoyées')
    # Signaler les erreurs partielles dans les logs, sans empêcher la publication des autres sports.
    return 1 if len(errors) == len(SPORTS) else 0

if __name__ == '__main__':
    try:
        sys.exit(run())
    except (ValueError, RuntimeError, KeyError, urllib.error.HTTPError, urllib.error.URLError) as ex:
        print(f'ERREUR CRITIQUE {type(ex).__name__}: {ex}',file=sys.stderr)
        sys.exit(1)
