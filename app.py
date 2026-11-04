#!/usr/bin/env python3
"""NHL Point Radar, API + mobile site. No external Python dependencies."""
import concurrent.futures
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import urlopen, Request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = {}
LOCK = threading.Lock()
LIMIT = max(40, min(250, int(os.environ.get("PLAYER_LIMIT", "140"))))
TIMEOUT = float(os.environ.get("NHL_TIMEOUT", "12"))
WORKERS = min(16, max(2, int(os.environ.get("FETCH_WORKERS", "12"))))

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def season_now():
    year = datetime.now(timezone.utc).year
    return str(year if datetime.now(timezone.utc).month >= 9 else year - 1) + str(year + 1 if datetime.now(timezone.utc).month >= 9 else year)

def nhl(url, params=None):
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 NHLPointRadar/2", "Accept": "application/json"})
    with urlopen(req, timeout=TIMEOUT) as f:
        return json.load(f)

def integer(x):
    try:
        return int(x or 0)
    except (ValueError, TypeError):
        return 0

def summarize(rows, number):
    recent = rows[-number:]
    n = len(recent)
    wins = sum(g["points"] > 0 for g in recent)
    return {"matches": n, "withPoint": wins, "rate": round(100*wins/n, 1) if n else None,
            "goals": sum(g["goals"] for g in recent),
            "assists": sum(g["assists"] for g in recent)}

def player(row, season):
    pid = integer(row.get("playerId"))
    if not pid:
        return None
    raw = nhl("https://api-web.nhle.com/v1/player/%s/game-log/%s/2" % (pid, season))
    logs = raw.get("gameLog") or []
    rows = [{"date": str(g.get("gameDate") or "")[:10],
             "opponent": g.get("opponentAbbrev") or "",
             "goals": integer(g.get("goals")), "assists": integer(g.get("assists")),
             "points": integer(g.get("goals"))+integer(g.get("assists"))} for g in logs if g.get("gameDate")]
    rows.sort(key=lambda g: g["date"])
    if not rows:
        return None
    season_stats = summarize(rows, len(rows))
    last10 = summarize(rows, 10)
    last5 = summarize(rows, 5)
    goals, assists = season_stats["goals"], season_stats["assists"]
    total = goals + assists
    share = goals/total if total else 0
    # Descriptive index, NOT a modeled probability of next-game success
    score = round(100 * (.4*(season_stats["withPoint"]+3)/(len(rows)+6)
                         + .4*(last10["withPoint"]+3)/(last10["matches"]+6)
                         + .2*(last5["withPoint"]+2)/(last5["matches"]+4)), 1)
    return {"id":pid,"name":row.get("skaterFullName") or str(pid),
            "team":str(row.get("teamAbbrevs") or ""), "position":row.get("positionCode") or "",
            "games":len(rows), "goals":goals, "assists":assists, "points":total,
            "pointGames":season_stats["withPoint"], "seasonRate":season_stats["rate"],
            "last10":last10,"last5":last5,"index":score, "recentGames":rows[-10:],
            "profile":"Polyvalent" if .25 <= share <= .75 else "Buteur" if share > .75 else "Passeur"}

def all_players(season):
    params = {"isAggregate":"false","isGame":"false","start":0,"limit":LIMIT,
              "sort":json.dumps([{"property":"points","direction":"DESC"}], separators=(",",":")),
              "cayenneExp":"seasonId=%s and gameTypeId=2" % season}
    source = []
    offset = 0
    while len(source) < LIMIT:
        params["start"] = offset
        params["limit"] = min(100, LIMIT - len(source))
        resp = nhl("https://api.nhle.com/stats/rest/en/skater/summary", params)
        batch = resp.get("data") or []
        if not batch:
            break
        source.extend(batch)
        offset += len(batch)
        if len(batch) < params["limit"]:
            break
    if not source:
        raise RuntimeError("Pas de statistiques disponibles pour cette saison.")
    unique = {}
    for item in source:
        pid = integer(item.get("playerId"))
        if pid and (pid not in unique or integer(item.get("points")) > integer(unique[pid].get("points"))):
            unique[pid] = item
    people, failed = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(player, item, season) for item in unique.values()]
        for f in concurrent.futures.as_completed(futures):
            try:
                result = f.result()
                if result:
                    people.append(result)
                else:
                    failed += 1
            except Exception:
                failed += 1
    if not people:
        raise RuntimeError("Aucun historique individuel reçu de la NHL.")
    people.sort(key=lambda p:(-p["index"],-p["points"],p["name"]))
    return {"season":season,"updatedAt":now(),"players":people,
            "tracked":len(people),"selectedTop":len(unique),"failedHistories":failed,
            "partial":failed > 0, "source":"NHL API",
            "method":"Match avec 1+ point = but ou passe. Indice descriptif, pas une probabilité de pari."}

def games_for(day):
    raw = nhl("https://api-web.nhle.com/v1/score/"+day)
    if not isinstance(raw.get("games"),list):
        raise RuntimeError("Format calendrier NHL inattendu.")
    games = []
    for game in raw["games"]:
        if game.get("gameType") not in (None,2):
            continue
        away = (game.get("awayTeam") or {}).get("abbrev")
        home = (game.get("homeTeam") or {}).get("abbrev")
        if away and home:
            games.append({"id":integer(game.get("id")),"away":away,"home":home,
                          "state":game.get("gameState") or "UNKNOWN",
                          "startUTC":game.get("startTimeUTC") or "",
                          "awayScore":(game.get("awayTeam") or {}).get("score"),
                          "homeScore":(game.get("homeTeam") or {}).get("score")})
    games.sort(key=lambda g:g["startUTC"])
    return {"date":day,"games":games,"updatedAt":now()}

def cached(key, ttl, get):
    with LOCK:
        record = CACHE.get(key)
        if record and time.monotonic()-record[0] < ttl:
            return record[1]
    try:
        val = get()
        with LOCK:
            CACHE[key] = (time.monotonic(),val)
        return val
    except Exception as e:
        if record:
            return dict(record[1], stale=True, warning="Dernières données conservées : "+str(e))
        raise

class Handler(BaseHTTPRequestHandler):
    def json(self, body, status=200):
        data=json.dumps(body,ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        parsed=urlparse(self.path)
        route=parsed.path
        query=parse_qs(parsed.query)
        if route=="/api/health":
            return self.json({"ok":True,"utc":now(),"season":season_now()})
        if route=="/api/players":
            season=query.get("season",[season_now()])[0]
            if not re.fullmatch(r"20\d{6}",season) or int(season[4:])!=int(season[:4])+1:
                return self.json({"error":"Saison invalide."},400)
            try:
                return self.json(cached("players:"+season,900,lambda:all_players(season)))
            except Exception as e:
                return self.json({"error":"Données NHL indisponibles : "+str(e)},502)
        if route=="/api/games":
            day=query.get("date",[datetime.now(timezone.utc).date().isoformat()])[0]
            try:
                datetime.strptime(day,"%Y-%m-%d")
                if not re.fullmatch(r"20\d\d-\d\d-\d\d",day):
                    raise ValueError()
            except ValueError:
                return self.json({"error":"Date invalide."},400)
            try:
                return self.json(cached("games:"+day,300,lambda:games_for(day)))
            except Exception as e:
                return self.json({"error":"Calendrier NHL indisponible : "+str(e)},502)
        file_path = BASE / "static" / ("index.html" if route=="/" else route.removeprefix("/"))
        if not file_path.resolve().is_relative_to((BASE/"static").resolve()) or not file_path.is_file():
            self.send_error(404)
            return
        mime = {".html":"text/html; charset=utf-8",".js":"application/javascript; charset=utf-8",
                ".css":"text/css; charset=utf-8",".svg":"image/svg+xml",".webmanifest":"application/manifest+json"}.get(file_path.suffix,"application/octet-stream")
        data=file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",mime)
        self.send_header("Cache-Control","public, max-age=300")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__=="__main__":
    port=int(os.environ.get("PORT","10000"))
    print("NHL Point Radar listening on",port,flush=True)
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
