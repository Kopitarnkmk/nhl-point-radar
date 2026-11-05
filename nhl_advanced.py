"""NHL matchup forecasts — descriptive baseline, not official betting probabilities."""
import math
from datetime import datetime,timezone
from urllib.parse import quote

def _num(x,fallback=None):
    try:return float(x)
    except (TypeError,ValueError):return fallback
def _p(lamb,k):
    if k<0:return 0
    return math.exp(-lamb)*lamb**k/math.factorial(k)
def _poisson_match(a,b):
    win=loss=tie=0.0
    for i in range(19):
        for j in range(19):
            v=_p(a,i)*_p(b,j)
            if i>j:win+=v
            elif i<j:loss+=v
            else:tie+=v
    return round(100*(win+.5*tie),1),round(100*(loss+.5*tie),1),round(100*tie,1)
def game_preview(nhl, game_id, season):
    base=f"https://api-web.nhle.com/v1/gamecenter/{int(game_id)}"
    land=nhl(base+"/landing")
    home=land.get("homeTeam") or {};away=land.get("awayTeam") or {}
    ha=home.get("abbrev");aa=away.get("abbrev")
    if not ha or not aa:raise ValueError("Match NHL sans deux équipes valides.")
    def club(abbr):
        data=nhl(f"https://api-web.nhle.com/v1/club-schedule-season/{quote(abbr)}/{season}")
        seen=[]
        # Includes all played game states only
        for g in data.get("games",[]):
            if g.get("gameType")!=2 or g.get("gameState") not in ("OFF","FINAL"):
                continue
            h=g.get("homeTeam") or {};a=g.get("awayTeam") or {}
            sh=_num(h.get("score"));sa=_num(a.get("score"))
            if sh is None or sa is None:continue
            if h.get("abbrev")==abbr:seen.append((g["startTimeUTC"],sh,sa))
            elif a.get("abbrev")==abbr:seen.append((g["startTimeUTC"],sa,sh))
        seen.sort(reverse=True)
        take=seen[:10];n=len(take)
        gf=sum(x[1] for x in take)/n if n else None
        ga=sum(x[2] for x in take)/n if n else None
        return {"games":n,"gf":round(gf,2) if gf is not None else None,"ga":round(ga,2) if ga is not None else None,
                "wins":sum(x[1]>x[2] for x in take),"record":"%d / %d"%(sum(x[1]>x[2] for x in take),n)}
    hstats=club(ha);astats=club(aa)
    valid=hstats["games"]>=5 and astats["games"]>=5
    # Home advantage and league baseline; shrink toward 3.0 to avoid overfitting 10 games.
    if valid:
        hmu=.35*3+.65*(hstats["gf"]+astats["ga"])/2+0.13
        amu=.35*3+.65*(astats["gf"]+hstats["ga"])/2-0.13
        hmu=max(.8,min(5.7,hmu));amu=max(.8,min(5.7,amu))
        hw,aw,tie=_poisson_match(hmu,amu)
        model={"homeGoals":round(hmu,2),"awayGoals":round(amu,2),"totalGoals":round(hmu+amu,2),
               "homeWinPct":hw,"awayWinPct":aw,"regulationTiePct":tie,
               "method":"Poisson simple, 10 derniers matchs terminés, régression vers 3 buts/équipe, léger effet domicile; prolongation départagée à 50/50. Pas de cotes ni blessés.",
               "label":"Estimation indicative — NON calibrée contre les bookmakers","sample":min(hstats["games"],astats["games"])}
    else:model=None
    comparisons=(land.get("matchup") or {}).get("goalieComparison") or {}
    def goalie_list(which):
        part=comparisons.get(which) or {}
        return [{"id":int(g.get("playerId") or 0),"name":(g.get("firstName") or {}).get("default","")+" "+(g.get("lastName") or {}).get("default",""),
                 "savePct":round(100*_num(g.get("savePctg"),0),2) if g.get("savePctg") is not None else None,
                 "gaa":_num(g.get("gaa")),"starts":g.get("gamesPlayed"),"record":g.get("record")}
                 for g in part.get("leaders") or [] if g.get("playerId")]
    goalies={"home":goalie_list("homeTeam"),"away":goalie_list("awayTeam")}
    official={"home":[],"away":[]}
    lineup={"home":[],"away":[]}
    state=land.get("gameState") or "FUT"
    if state not in ("FUT","PRE"):
        try:
            box=nhl(base+"/boxscore")
            for side in ("home","away"):
                b=(box.get("playerByGameStats") or {}).get(side+"Team") or {}
                lineup[side]=[{"name":(s.get("name") or {}).get("default") or "","position":s.get("position"),"toi":s.get("toi")}
                              for group in ("forwards","defense","goalies") for s in b.get(group) or [] if s.get("name")]
                official[side]=[{"id":g.get("playerId"),"name":(g.get("name") or {}).get("default"),"savePctInGame":g.get("savePctg")}
                                for g in b.get("goalies") or [] if g.get("toi") and g.get("toi")!="00:00"]
        except Exception:pass
    return {"gameId":int(game_id),"updatedAt":datetime.now(timezone.utc).isoformat(),"state":state,"home":ha,"away":aa,
            "teams":{"home":hstats,"away":astats},"model":model,"goalies":goalies,"starters":official,
            "lineup":lineup,"lineupStatus":"Feuille de match NHL" if lineup["home"] or lineup["away"] else "Composition officielle non publiée",
            "goalieStatus":"En jeu (confirmé par temps de glace)" if official["home"] or official["away"] else "Titulaire non confirmé — liste de candidats"}
