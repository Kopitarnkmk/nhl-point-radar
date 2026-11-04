#!/usr/bin/env python3
"""Football Point Radar — browser dashboard, ESPN match data (unofficial, keyless)."""
import concurrent.futures
import json
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
SPORT = "https://site.api.espn.com/apis/site/v2/sports/soccer"
COMPETITIONS = [
    ("eng.1","Premier League","championnat","Angleterre"),
    ("esp.1","La Liga","championnat","Espagne"),
    ("ger.1","Bundesliga","championnat","Allemagne"),
    ("ita.1","Serie A","championnat","Italie"),
    ("fra.1","Ligue 1","championnat","France"),
    ("por.1","Liga Portugal","championnat","Portugal"),
    ("ned.1","Eredivisie","championnat","Pays-Bas"),
    ("sui.1","Super League suisse","championnat","Suisse"),
    ("bel.1","Pro League belge","championnat","Belgique"),
    ("tur.1","Süper Lig","championnat","Turquie"),
    ("eng.fa","FA Cup","coupe","Angleterre"),
    ("eng.league_cup","Carabao Cup","coupe","Angleterre"),
    ("esp.copa_del_rey","Copa del Rey","coupe","Espagne"),
    ("ger.dfb_pokal","DFB-Pokal","coupe","Allemagne"),
    ("ita.coppa_italia","Coppa Italia","coupe","Italie"),
    ("fra.coupe_de_france","Coupe de France","coupe","France"),
    ("uefa.champions","Ligue des champions","europe","Europe"),
    ("uefa.europa","Europa League","europe","Europe"),
    ("uefa.europa.conf","Conference League","europe","Europe"),
]
CAT = {c[0]: {"id":c[0], "name":c[1], "kind":c[2], "country":c[3]} for c in COMPETITIONS}
CACHE = {}
LOCK = threading.RLock()
TIMEOUT = 22
POOL = 7

def utcnow(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def fetch(url, params=None):
    if params: url += "?" + urlencode(params)
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 FootballPointRadar/1", "Accept":"application/json"})
    with urlopen(req, timeout=TIMEOUT) as response:
        return json.load(response)

def cache(key, ttl, fn):
    with LOCK:
        entry = CACHE.get(key)
        if entry and time.monotonic()-entry[0] < ttl: return entry[1]
    try:
        val=fn()
        with LOCK: CACHE[key]=(time.monotonic(),val)
        return val
    except Exception:
        if entry is not None:
            return dict(entry[1], stale=True)
        raise

def parse_event(e, league):
    comp = (e.get("competitions") or [{}])[0]
    members = comp.get("competitors") or []
    home = next((a for a in members if a.get("homeAway")=="home"),None)
    away = next((a for a in members if a.get("homeAway")=="away"),None)
    if not home or not away: return None
    status = (e.get("status") or {}).get("type") or {}
    def t(z):
        team=z.get("team") or {}
        score=z.get("score")
        try: score=int(score) if score is not None else None
        except (ValueError,TypeError): score=None
        return {"id":str(team.get("id") or ""), "name":team.get("displayName") or team.get("name") or "?",
                "abbr":team.get("abbreviation") or "", "logo":team.get("logo") or "", "goals":score}
    h,a=t(home),t(away)
    season=e.get("season") or {}
    stage = (season.get("slug") or "").replace("-"," ").title()
    notes=comp.get("notes") or []
    if notes and isinstance(notes,list):
        first=notes[0]
        if isinstance(first,dict) and first.get("headline"): stage=str(first.get("headline"))[:95]
    return {"id":str(e.get("id") or ""),"competition":league,"kind":CAT[league]["kind"],"country":CAT[league]["country"],
            "competitionName":CAT[league]["name"],"stage":stage,
            "date":e.get("date") or "","state":status.get("state") or "pre",
            "completed":bool(status.get("completed")),
            "status":status.get("description") or "",
            "home":h,"away":a}

def season_start():
    d=date.today()
    year=d.year if d.month>=7 else d.year-1
    return date(year,7,1)

def season_years():
    d=date.today()
    if d.month>=7: return [d.year]
    return [d.year-1,d.year]

def day_fixture(comp, ymd):
    raw=fetch(SPORT+"/"+comp+"/scoreboard",{"dates":ymd.replace("-",""),"limit":250})
    if not isinstance(raw.get("events"),list): raise ValueError("Réponse ESPN incorrecte")
    out=[]
    for e in raw["events"]:
        match=parse_event(e,comp)
        if match and match["id"]: out.append(match)
    return out

def schedule(ymd):
    found=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=POOL) as pool:
        task={pool.submit(day_fixture,c,ymd): c for c in CAT}
        for future in concurrent.futures.as_completed(task):
            comp=task[future]
            try: found.extend(future.result())
            except Exception as e: errors.append({"competition":comp,"reason":type(e).__name__})
    found.sort(key=lambda x:(x["date"],x["competition"]))
    return {"date":ymd,"fixtures":found,"errors":errors,"partial":bool(errors),"updatedAt":utcnow(),
            "note":"Compétitions ESPN : calendriers parfois incomplets; vérifier le bookmaker."}

def history(comp):
    if comp not in CAT: raise ValueError("Compétition inconnue")
    collected={};failed=[]
    for year in season_years():
        try:
            raw=fetch(SPORT+"/"+comp+"/scoreboard",{"dates":str(year),"limit":750})
        except Exception as e:
            failed.append(str(year)+":"+type(e).__name__)
            continue
        for event in raw.get("events") or []:
            parsed=parse_event(event,comp)
            if not parsed or not parsed["completed"] or parsed["home"]["goals"] is None or parsed["away"]["goals"] is None: continue
            try:
                when=date.fromisoformat(parsed["date"][:10])
            except ValueError:continue
            # Separate current European season from previous season, not all calendar-year games.
            if when<season_start() or when>date.today():continue
            collected[parsed["id"]]=parsed
    games=sorted(collected.values(),key=lambda e:e["date"])
    if not games and failed: raise RuntimeError("Historique ESPN inaccessible : "+", ".join(failed))
    return {"competition":CAT[comp],"games":games,"total":len(games),"partial":bool(failed),
            "errors":failed,"updatedAt":utcnow(),"seasonStart":season_start().isoformat()}

def jsondata(handler, obj, status=200):
    data=json.dumps(obj,ensure_ascii=False,separators=(",",":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type","application/json; charset=utf-8")
    handler.send_header("Cache-Control","no-store")
    handler.send_header("Content-Length",str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try: self.route()
        except BrokenPipeError: pass
        except Exception as e:
            try:jsondata(self,{"error":"Données temporairement indisponibles : "+str(e)},502)
            except Exception:pass
    def route(self):
        parsed=urlparse(self.path)
        route=parsed.path
        query=parse_qs(parsed.query)
        if route=="/api/health":
            return jsondata(self,{"ok":True,"service":"football-point-radar","utc":utcnow()})
        if route=="/api/competitions":
            return jsondata(self,{"competitions":list(CAT.values())})
        if route=="/api/fixtures":
            day=query.get("date",[date.today().isoformat()])[0]
            try:
                if not re.fullmatch(r"20\d\d-\d\d-\d\d",day):raise ValueError()
                date.fromisoformat(day)
            except ValueError:return jsondata(self,{"error":"Date invalide"},400)
            result=cache("schedule:"+day,300,lambda:schedule(day))
            return jsondata(self,result)
        if route=="/api/history":
            comp=query.get("competition",[""])[0]
            if comp not in CAT:return jsondata(self,{"error":"Compétition inconnue"},400)
            result=cache("history:"+comp,3600,lambda:history(comp))
            return jsondata(self,result)
        filename="index.html" if route=="/" else route.lstrip("/")
        filepath=(BASE/"static"/filename).resolve()
        if not filepath.is_relative_to((BASE/"static").resolve()) or not filepath.is_file():
            self.send_error(404);return
        data=filepath.read_bytes()
        mime={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".svg":"image/svg+xml",".webmanifest":"application/manifest+json"}.get(filepath.suffix,"application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","public,max-age=180")
        self.end_headers()
        self.wfile.write(data)

if __name__=="__main__":
    port=int(os.environ.get("PORT","10000"))
    print("Football Point Radar listening on",port,flush=True)
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
