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


def leaders_for(comp):
    """Season goal / assist leaderboard. ESPN uses season's first calendar year (2026 for 2026-27)."""
    if comp not in CAT: raise ValueError("Compétition inconnue")
    start=season_start().year
    path=f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{comp}/seasons/{start}/types/1/leaders"
    raw=fetch(path,{"limit":22})
    categories={x.get("name"):x.get("leaders") or [] for x in raw.get("categories") or []}
    players={}
    for kind,arr in (("goals",categories.get("goalsLeaders") or categories.get("goals") or []),
                     ("assists",categories.get("assistsLeaders") or categories.get("assists") or [])):
        for r in arr[:22]:
            athlete_ref=(r.get("athlete") or {}).get("$ref","")
            team_ref=(r.get("team") or {}).get("$ref","")
            player_id=re.search(r"/athletes/(\d+)",athlete_ref)
            team_id=re.search(r"/teams/(\d+)",team_ref)
            if not player_id: continue
            pid=player_id.group(1)
            if pid not in players:
                players[pid]={"id":pid,"teamId":team_id.group(1) if team_id else "",
                              "name":"","teamName":"","goals":0,"assists":0,"matches":0,
                              "source":"ESPN leaderboards"}
            p=players[pid]
            vals=str(r.get("shortDisplayValue") or "")
            match=re.search(r"\bM:\s*(\d+)",vals)
            if match:p["matches"]=max(p["matches"],int(match.group(1)))
            goal=re.search(r"\bG:\s*(\d+)",vals)
            assist=re.search(r"\bA:\s*(\d+)",vals)
            if goal:p["goals"]=max(p["goals"],int(goal.group(1)))
            if assist:p["assists"]=max(p["assists"],int(assist.group(1)))
            if kind=="goals":p["goals"]=max(p["goals"],int(r.get("value") or 0))
            else:p["assists"]=max(p["assists"],int(r.get("value") or 0))
    ordered=sorted(players.values(),key=lambda p:(-p["goals"],-p["assists"]))[:28]
    def resolve_player(p):
        try:
            url=f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{comp}/seasons/{start}/athletes/{p['id']}"
            person=fetch(url)
            p["name"]=person.get("fullName") or person.get("displayName") or ""
        except Exception: pass
        return p
    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
        ordered=list(pool.map(resolve_player,ordered))
    # Resolve each club once. Clubs must be grounded in provider data.
    ids=set(p["teamId"] for p in ordered if p["teamId"])
    def resolve_team(teamid):
        try:
            club=fetch(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{comp}/seasons/{start}/teams/{teamid}")
            return teamid,club.get("displayName") or club.get("name") or ""
        except Exception:
            return teamid,""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        clubnames=dict(pool.map(resolve_team,ids))
    for p in ordered:
        p["teamName"]=clubnames.get(p["teamId"],"")
    # A missing athlete identity is omitted, never replaced by an invented player.
    ordered=[p for p in ordered if p["name"] and p["matches"]>0]
    ordered.sort(key=lambda p:(-p["goals"],-p["assists"],p["name"]))
    return {"competition":CAT[comp],"players":ordered,"updatedAt":utcnow(),
            "sampleNote":"Buts / matchs n'est pas la probabilité de marquer au prochain match. Joueurs non titulaires possibles.",
            "coverage":"Classement partiel des meilleurs buteurs/passeurs, pas tous les joueurs."}

def next_fixtures(from_day,chosen):
    """Quick jump to upcoming fixtures using one yearly league request per selected competition."""
    options=[k for k,v in CAT.items() if chosen=="all" or chosen==v["kind"] or chosen==k]
    if chosen=="all":
        # Fast, representative next match across key leagues; full list remains available by date.
        options=["eng.1","esp.1","ger.1","ita.1","fra.1","uefa.champions","uefa.europa","uefa.europa.conf"]
    if not options: raise ValueError("Filtre non reconnu")
    def read_one(comp):
        found=[]
        for year in [date.fromisoformat(from_day).year]:
            raw=fetch(SPORT+"/"+comp+"/scoreboard",{"dates":str(year),"limit":750})
            for event in raw.get("events") or []:
                m=parse_event(event,comp)
                if m and m["state"]=="pre" and m["date"][:10]>=from_day:
                    found.append(m)
        return found
    found=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        futures={pool.submit(read_one,k):k for k in options}
        for future in concurrent.futures.as_completed(futures):
            try:found+=future.result()
            except Exception:pass
    found.sort(key=lambda x:x["date"])
    earliest=found[0]["date"][:10] if found else None
    return {"date":earliest,"filter":chosen,"count":len(found),"examples":found[:8],"updatedAt":utcnow()}

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
        if route=="/api/leaders":
            comp=query.get("competition",[""])[0]
            if comp not in CAT:return jsondata(self,{"error":"Compétition inconnue"},400)
            return jsondata(self,cache("leaders:"+comp,3600,lambda:leaders_for(comp)))
        if route=="/api/next":
            chosen=query.get("filter",["all"])[0]
            day=query.get("date",[date.today().isoformat()])[0]
            if chosen not in list(CAT)+["all","championnat","coupe","europe"]:return jsondata(self,{"error":"Filtre invalide"},400)
            try: date.fromisoformat(day)
            except ValueError:return jsondata(self,{"error":"Date invalide"},400)
            return jsondata(self,cache("next:"+chosen+":"+day,1800,lambda:next_fixtures(day,chosen)))
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
