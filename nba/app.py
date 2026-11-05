"""NBA Radar — keyless ESPN stats, illustrative estimates, stdlib only."""
import concurrent.futures, json, math, os, re, threading, time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,urlencode
from urllib.request import Request,urlopen
BASE=Path(__file__).resolve().parent;CACHE={};LOCK=threading.RLock()
SRC="https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
LOGS="https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"
def fetch(url,params=None):
 if params:url+="?"+urlencode(params)
 with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 NBA-Radar/1","Accept":"application/json"}),timeout=18) as r:return json.load(r)
def cache(key,ttl,fn):
 with LOCK:
  obj=CACHE.get(key)
  if obj and time.monotonic()-obj[0]<ttl:return obj[1]
 try:
  v=fn()
  with LOCK:CACHE[key]=(time.monotonic(),v)
  return v
 except Exception:
  if obj:return dict(obj[1],stale=True)
  raise
def season():
 d=datetime.now(timezone.utc)
 return d.year+1 if d.month>=9 else d.year
def fnum(v):
 try:return float(v)
 except (ValueError,TypeError):return None
def fixtures(day):
 raw=fetch(SRC+"/scoreboard",{"dates":day.replace("-",""),"limit":100})
 out=[]
 for e in raw.get("events") or []:
  teams=(e.get("competitions") or [{}])[0].get("competitors") or []
  home=next((t for t in teams if t.get("homeAway")=="home"),None)
  away=next((t for t in teams if t.get("homeAway")=="away"),None)
  if not home or not away:continue
  def t(x):
   team=x.get("team") or {}
   return {"id":str(team.get("id")),"name":team.get("displayName"),"abbr":team.get("abbreviation"),
           "logo":team.get("logo"),"score":fnum(x.get("score"))}
  status=(e.get("status") or {}).get("type") or {}
  out.append({"id":str(e["id"]),"date":e.get("date"),"home":t(home),"away":t(away),
              "state":status.get("state"),"completed":bool(status.get("completed"))})
 return {"date":day,"games":out,"updatedAt":datetime.now(timezone.utc).isoformat(),"source":"ESPN"}
def team_form(tid,cutoff):
 raw=fetch(SRC+f"/teams/{tid}/schedule",{"dates":str(season()),"limit":150})
 rows=[]
 for e in raw.get("events") or []:
  cs=(e.get("competitions") or [{}])[0].get("competitors") or []
  a=next((x for x in cs if str((x.get("team") or {}).get("id"))==tid),None)
  b=next((x for x in cs if str((x.get("team") or {}).get("id"))!=tid),None)
  if not a or not b:continue
  status=(e.get("competitions") or [{}])[0].get("status") or e.get("status") or {}
  if status and not (status.get("type") or status).get("completed"):continue
  def score(t):
   s=t.get("score")
   if isinstance(s,dict):return fnum(s.get("value"))
   return fnum(s)
  aa,bb=score(a),score(b)
  if aa is None or bb is None:continue
  # Strictly prior completed games: never train on the event being analysed.
  if not e.get("date") or e["date"]>=cutoff:continue
  rows.append((e.get("date") or "",aa,bb))
 rows.sort(key=lambda x:x[0],reverse=True);rows=rows[:10]
 n=len(rows)
 return {"games":n,"scored":round(sum(x[1] for x in rows)/n,1) if n else None,
         "allowed":round(sum(x[2] for x in rows)/n,1) if n else None,
         "wins":sum(x[1]>x[2] for x in rows)}
def analyze_team(game):
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
  h=ex.submit(team_form,game["home"]["id"],game["date"]);a=ex.submit(team_form,game["away"]["id"],game["date"])
  hs=h.result();aw=a.result()
 model=None
 if hs["games"]>=4 and aw["games"]>=4:
  home=max(80,min(142,.35*113+.65*(hs["scored"]+aw["allowed"])/2+1.5))
  away=max(80,min(142,.35*113+.65*(aw["scored"]+hs["allowed"])/2-1.5))
  z=(home-away)/17
  # Normal CDF from past points, not calibrated on bookmakers
  prob=100*(.5*(1+math.erf(z/math.sqrt(2))))
  model={"homeScore":round(home,1),"awayScore":round(away,1),"total":round(home+away,1),
         "homeWinPct":round(prob,1),"awayWinPct":round(100-prob,1),
         "method":"Moyennes points pour/contre des 10 derniers matchs, retour vers 113 pts, +3 pts domicile; loi normale écart-type 17 pts. Non calibré.","sample":min(hs["games"],aw["games"])}
 return {"model":model,"home":hs,"away":aw}
def roster(team_id):
 raw=fetch(SRC+f"/teams/{team_id}/roster")
 result=[]
 for p in raw.get("athletes") or []:
  if not p.get("id"):continue
  result.append({"id":str(p["id"]),"name":p.get("displayName") or p.get("fullName"),
                 "position":(p.get("position") or {}).get("abbreviation"),
                 "status":(p.get("status") or {}).get("name"),"injuries":p.get("injuries") or [],"out":any(str(i.get("status") or "").strip().lower() in ("out","doubtful","inactive") for i in p.get("injuries") or [])})
 return result
def player_log(pid,cutoff,excluded_event_id):
 raw=fetch(LOGS+f"/athletes/{pid}/gamelog",{"season":season()})
 names=raw.get("names") or []
 groups=[x for x in raw.get("seasonTypes") or [] if "Regular Season" in x.get("displayName","")]
 out=[]
 for block in groups:
  for cat in block.get("categories") or []:
   for item in cat.get("events") or []:
    event_id=str(item.get("eventId") or "")
    event_info=(raw.get("events") or {}).get(event_id) or {}
    played=event_info.get("gameDate") or ""
    # Date and event ID filter prevent target-match outcome leakage.
    if not played or played>=cutoff or event_id==str(excluded_event_id):continue
    stats=item.get("stats") or []
    data=dict(zip(names,stats))
    def stat(k):
     val=data.get(k)
     return fnum(val)
    fg=data.get("fieldGoalsMade-fieldGoalsAttempted") or "0-0"
    three=data.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted") or "0-0"
    fgmade=fnum(str(fg).split("-")[0]);threemade=fnum(str(three).split("-")[0])
    if fgmade is None or threemade is None:continue
    out.append({"date":played,"id":event_id,"points":stat("points"),"rebounds":stat("totalRebounds"),
                "assists":stat("assists"),"threes":threemade,"twos":max(0,fgmade-threemade),
                "blocks":stat("blocks"),"steals":stat("steals"),"minutes":stat("minutes")})
 out.sort(key=lambda r:r["date"],reverse=True)
 return out
def player_forecast(p,cutoff,excluded_event_id):
 try:rows=player_log(p["id"],cutoff,excluded_event_id)
 except Exception:return None
 if not rows:return None
 stats={}
 for key in ("points","rebounds","assists","twos","threes","blocks","steals","minutes"):
  vals=[r[key] for r in rows if r.get(key) is not None]
  if not vals:continue
  mean10=sum(vals[:10])/len(vals[:10]);mean5=sum(vals[:5])/len(vals[:5])
  stats[key]=round(.6*mean5+.4*mean10,1)
 return dict(p,projection=stats,history={k:[r[k] for r in rows[:10] if r.get(k) is not None] for k in stats},games=len(rows),sample=min(10,len(rows)),method="Moyenne pondérée 5/10 derniers matchs de saison régulière, non ajustée aux absences ni à l'adversaire.")
def game_report(gid,day):
 g=next((x for x in fixtures(day)["games"] if x["id"]==gid),None)
 if not g:raise ValueError("Match introuvable pour la date.")
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
  hp=ex.submit(roster,g["home"]["id"]);ap=ex.submit(roster,g["away"]["id"]);tm=ex.submit(analyze_team,g)
  home_players=hp.result();away_players=ap.result();models=tm.result()
 # Restrict to a manageable set: first 12 roster players per team; include sample size
 both=[(g["home"]["abbr"],p) for p in home_players[:15]]+[(g["away"]["abbr"],p) for p in away_players[:15]]
 players=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=9) as ex:
  tasks={ex.submit(player_forecast,p,g["date"],gid):abbr for abbr,p in both}
  for future in concurrent.futures.as_completed(tasks):
   try:
    q=future.result()
    if q and q.get("projection"):q["team"]=tasks[future];players.append(q)
   except Exception:continue
 players.sort(key=lambda p:p["projection"].get("points",0),reverse=True)
 # Starting five are shown only if ESPN explicitly marks athletes as starters.
 starters=[];actuals=[]
 try:
  summary=fetch(SRC+"/summary",{"event":gid})
  for block in (summary.get("boxscore") or {}).get("players") or []:
   team=block.get("team") or {}
   if g["completed"]:
    for st in block.get("statistics") or []:
     labels=st.get("names") or []
     for ath in st.get("athletes") or []:
      p=ath.get("athlete") or {}
      raw=dict(zip(labels,ath.get("stats") or []))
      def number(k):return fnum(raw.get(k))
      fg=raw.get("FG") or "0-0";three=raw.get("3PT") or "0-0"
      fgmade=fnum(str(fg).split("-")[0]);three_made=fnum(str(three).split("-")[0])
      actuals.append({"id":str(p.get("id") or ""),"name":p.get("displayName"),
        "team":team.get("abbreviation"),"points":number("PTS"),"rebounds":number("REB"),
        "assists":number("AST"),"twos":(fgmade-three_made if fgmade is not None and three_made is not None else None),
        "threes":three_made,"steals":number("STL"),"blocks":number("BLK")})
   names=[]
   for st in block.get("statistics") or []:
    for athlete in st.get("athletes") or []:
     if athlete.get("starter") is True:
      names.append((athlete.get("athlete") or {}).get("displayName") or "")
   names=list(dict.fromkeys(x for x in names if x))
   if names:starters.append({"team":team.get("displayName"),"players":names})
 except Exception:pass
 return {"game":g,"teamProjection":models,"players":players,"actuals":actuals,"asOf":g["date"],"retrospective":datetime.fromisoformat(g["date"].replace("Z","+00:00"))<=datetime.now(timezone.utc), "historicalWindow":"Données des matchs antérieurs au coup d’envoi uniquement","starters":starters,
         "lineupStatus":"Cinq de départ indiqués par ESPN" if starters else "Effectifs listés ; cinq de départ non confirmés",
         "updatedAt":datetime.now(timezone.utc).isoformat()}
def send(h,obj,status=200):
 raw=json.dumps(obj,ensure_ascii=False).encode();h.send_response(status)
 h.send_header("Content-Type","application/json; charset=utf-8")
 h.send_header("Cache-Control","no-store");h.send_header("Content-Length",str(len(raw)));h.end_headers();h.wfile.write(raw)
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  u=urlparse(self.path);args=parse_qs(u.query)
  try:
   if u.path=="/api/health":return send(self,{"ok":True,"service":"nba-radar"})
   if u.path=="/api/games":
    day=args.get("date",[datetime.now(timezone.utc).date().isoformat()])[0]
    if not re.fullmatch(r"20\d\d-\d\d-\d\d",day):return send(self,{"error":"Date invalide"},400)
    return send(self,cache("games:"+day,300,lambda:fixtures(day)))
   if u.path=="/api/report":
    gid=args.get("id",[""])[0];day=args.get("date",[""])[0]
    if not re.fullmatch(r"\d{8,12}",gid) or not re.fullmatch(r"20\d\d-\d\d-\d\d",day):return send(self,{"error":"Date ou ID invalide"},400)
    return send(self,cache("report:"+gid,1200,lambda:game_report(gid,day)))
   path=(BASE/"static"/("index.html" if u.path=="/" else u.path.lstrip("/"))).resolve()
   if not path.is_relative_to((BASE/"static").resolve()) or not path.is_file():return self.send_error(404)
   content=path.read_bytes()
   mime={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".svg":"image/svg+xml",".webmanifest":"application/manifest+json"}.get(path.suffix,"application/octet-stream")
   self.send_response(200);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(content)));self.end_headers();self.wfile.write(content)
  except BrokenPipeError:pass
  except Exception as e:
   try:send(self,{"error":str(e)},502)
   except Exception:pass
if __name__=="__main__":ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),H).serve_forever()
