"""Football matchup baseline, lineups when ESPN has released them."""
import math
from datetime import datetime,timezone

def poisson(lamb,k):
    return math.exp(-lamb)*lamb**k/math.factorial(k)
def _side(items,id):
    found=[]
    for g in items:
        if g["home"]["id"]==id: found.append((g["date"],g["home"]["goals"],g["away"]["goals"],True))
        elif g["away"]["id"]==id:found.append((g["date"],g["away"]["goals"],g["home"]["goals"],False))
    found.sort(key=lambda r:r[0],reverse=True)
    subset=found[:8]
    n=len(subset)
    return {"n":n,"for":sum(a[1] for a in subset)/n if n else None,
            "against":sum(a[2] for a in subset)/n if n else None}
def forecast(match,history,fetch,sport_url):
    games=[g for g in history.get("games",[]) if g["date"]<match["date"]]
    a=_side(games,match["home"]["id"]);b=_side(games,match["away"]["id"])
    model=None
    if a["n"]>=2 and b["n"]>=2:
        h=max(.25,min(3.3,.4*1.35+.6*(a["for"]+b["against"])/2+.12))
        v=max(.25,min(3.3,.4*1.35+.6*(b["for"]+a["against"])/2-.12))
        ph=pv=pd=0.0
        for i in range(12):
            for j in range(12):
                p=poisson(h,i)*poisson(v,j)
                if i>j:ph+=p
                elif i<j:pv+=p
                else:pd+=p
        model={"homeGoals":round(h,2),"awayGoals":round(v,2),"totalGoals":round(h+v,2),
               "homeWinPct":round(100*ph,1),"drawPct":round(100*pd,1),"awayWinPct":round(100*pv,1),
               "sample":min(a["n"],b["n"]),"uncertainty":"Forte" if min(a["n"],b["n"])<5 else "Modérée",
               "method":"Poisson simplifié sur les 8 derniers matchs dans cette compétition, avec retour vers 1,35 but/équipe et légère correction domicile. Indicateurs NON calibrés."}
    summary=fetch(sport_url+"/"+match["competition"]+"/summary",{"event":match["id"]})
    result={"eventId":match["id"],"competition":match["competition"],"updatedAt":datetime.now(timezone.utc).isoformat(),
            "model":model,"lineupStatus":"Non publiée / non confirmée", "lineups":[]}
    for side in summary.get("rosters") or []:
        team=side.get("team") or {}
        listed=[]
        for item in side.get("roster") or []:
            p=item.get("athlete") or {}
            listed.append({"name":p.get("displayName") or p.get("fullName"),"starter":item.get("starter"),
                           "position":(item.get("position") or {}).get("abbreviation")})
        if listed:
            confirmed=[x for x in listed if x["starter"] is True]
            result["lineups"].append({"team":team.get("displayName") or team.get("name"),
                                      "players":confirmed if confirmed else listed,
                                      "confirmed":bool(confirmed)})
    if any(x["confirmed"] for x in result["lineups"]):
        result["lineupStatus"]="Titularisations indiquées par ESPN (à vérifier)"
    return result
