"""Tennis Radar — verified ATP/WTA fixtures + rankings + observed recent form."""
import json,os,math,re,time,threading,concurrent.futures
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode,urlparse,parse_qs
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent
SRC="https://site.api.espn.com/apis/site/v2/sports/tennis"
CACHE={};LOCK=threading.RLock()
def fetch(url,params=None):
 if params:url+="?"+urlencode(params)
 with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 TennisRadar/1","Accept":"application/json"}),timeout=24) as r:return json.load(r)
def cached(key,ttl,fn):
 with LOCK:
  got=CACHE.get(key)
  if got and time.monotonic()-got[0]<ttl:return got[1]
 try:
  val=fn()
  with LOCK:CACHE[key]=(time.monotonic(),val)
  return val
 except Exception:
  if got:return dict(got[1],stale=True)
  raise
def competition_data(tour,start,end):
 return fetch(SRC+"/"+tour+"/scoreboard",{"dates":start.replace("-","")+"-"+end.replace("-","")})
def convert_tournament(tour,raw):
 games=[]
 for event in raw.get("events") or []:
  place=event.get("venue") or {}
  for group in event.get("groupings") or []:
   for match in group.get("competitions") or []:
    competitors=match.get("competitors") or []
    if len(competitors)!=2 or any(not c.get("athlete") for c in competitors):continue
    def player(c):
     a=c.get("athlete") or {}
     return {"id":str(c.get("id") or a.get("id") or ""),"name":a.get("displayName") or a.get("fullName") or "?",
             "winner":c.get("winner"),"sets":[x.get("value") for x in c.get("linescores") or []]}
    state=(match.get("status") or {}).get("type") or {}
    date=match.get("date") or ""
    if not date:continue
    games.append({"id":str(match.get("id")),"date":date,"tour":tour,"tournament":event.get("name") or "Tournoi",
                  "round":(match.get("round") or {}).get("displayName"),"state":state.get("state") or "pre",
                  "complete":bool(state.get("completed")), "surface":place.get("surface") or "Non renseignée",
                  "a":player(competitors[0]),"b":player(competitors[1])})
 return games
def rankings(tour):
 raw=fetch(SRC+"/"+tour+"/rankings")
 ranks=[]
 for grp in raw.get("rankings") or []:
  for p in grp.get("ranks") or []:
   a=p.get("athlete") or {}
   if not a.get("id"):continue
   ranks.append({"id":str(a["id"]),"name":a.get("displayName"),"rank":p.get("current"),"points":p.get("points")})
 return ranks[:350]
def data(day):
 start=(datetime.strptime(day,"%Y-%m-%d")-timedelta(days=30)).date().isoformat()
 finish=(datetime.strptime(day,"%Y-%m-%d")+timedelta(days=2)).date().isoformat()
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
  calls={ex.submit(competition_data,t,start,finish):("matches",t) for t in ("atp","wta")}
  calls.update({ex.submit(rankings,t):("rank",t) for t in ("atp","wta")})
  raw={};err=[]
  for fut in concurrent.futures.as_completed(calls):
   k,t=calls[fut]
   try:raw[(k,t)]=fut.result()
   except Exception as e:err.append(t+" "+k+":"+str(e))
 all_matches=[]
 ranks={}
 for tour in ("atp","wta"):
  if ("matches",tour) in raw:all_matches+=convert_tournament(tour,raw[("matches",tour)])
  for p in raw.get(("rank",tour),[]):ranks[(tour,p["id"])]=p
 # Both completed past and upcoming; current date local time selection filters by UTC date, slightly approximate
 future=[m for m in all_matches if m["date"][:10]==day]
 past=[m for m in all_matches if m["complete"] and m["date"][:10]<day]
 for m in future:
  players=(m["a"],m["b"])
  form=[]
  for p in players:
   pastp=[g for g in past if g["tour"]==m["tour"] and p["id"] in (g["a"]["id"],g["b"]["id"])]
   pastp.sort(key=lambda z:z["date"],reverse=True)
   sample=pastp[:10]
   wins=sum((g["a"] if g["a"]["id"]==p["id"] else g["b"]).get("winner") is True for g in sample)
   r=ranks.get((m["tour"],p["id"]),{})
   form.append({"rank":r.get("rank"),"rankingPoints":r.get("points"),
                "last10":len(sample),"last10Wins":wins,"last10WinPct":round(wins/len(sample)*100,1) if sample else None})
  m["a"].update(form[0]);m["b"].update(form[1])
  ra,rb=form[0]["rank"],form[1]["rank"]
  m["model"]=None
  if isinstance(ra,int) and isinstance(rb,int) and ra>0 and rb>0:
   # A conservative, rank-based prior, with limited recent-form influence; NOT an Elo rating.
   z=.85*math.log((rb+15)/(ra+15))
   if form[0]["last10"]>=4 and form[1]["last10"]>=4:
    z+=.5*(form[0]["last10Wins"]/form[0]["last10"]-form[1]["last10Wins"]/form[1]["last10"])
   prob=max(.20,min(.80,1/(1+math.exp(-z))))
   m["model"]={"aWinPct":round(prob*100,1),"bWinPct":round((1-prob)*100,1),
               "label":"Estimation exploratoire basée sur le classement et la forme récente disponible (non calibrée).",
               "limitations":"Ne tient pas compte du niveau sur surface, blessures, fatigue, ni cotes marché."}
 future.sort(key=lambda x:x["date"])
 return {"date":day,"matches":future,"ranksCount":len(ranks),"pastGames":len(past),"errors":err,
         "updatedAt":datetime.now(timezone.utc).isoformat()}
def send(h,obj,status=200):
 data=json.dumps(obj,ensure_ascii=False).encode();h.send_response(status)
 h.send_header("Content-Type","application/json; charset=utf-8")
 h.send_header("Cache-Control","no-store");h.send_header("Content-Length",str(len(data)));h.end_headers();h.wfile.write(data)
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  u=urlparse(self.path);q=parse_qs(u.query)
  try:
   if u.path=="/api/health":return send(self,{"ok":True,"service":"tennis-radar"})
   if u.path=="/api/matches":
    day=q.get("date",[datetime.now(timezone.utc).date().isoformat()])[0]
    if not re.fullmatch(r"20\d\d-\d\d-\d\d",day):return send(self,{"error":"Date invalide"},400)
    return send(self,cached("matches:"+day,1800,lambda:data(day)))
   path=(ROOT/"static"/("index.html" if u.path=="/" else u.path.lstrip("/"))).resolve()
   if not path.is_relative_to((ROOT/"static").resolve()) or not path.is_file():return self.send_error(404)
   raw=path.read_bytes();m={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".svg":"image/svg+xml",".webmanifest":"application/manifest+json"}
   self.send_response(200);self.send_header("Content-Type",m.get(path.suffix,"application/octet-stream"))
   self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
  except BrokenPipeError:pass
  except Exception as e:
   try:send(self,{"error":str(e)},502)
   except Exception:pass
if __name__=="__main__":ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),H).serve_forever()
