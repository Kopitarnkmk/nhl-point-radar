"use strict";
const $=id=>document.getElementById(id),s={date:"",games:[],report:null,selected:null,picks:[],odds:{}};
const esc=v=>String(v??"").replace(/[&<>"']/g,k=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[k]));
const local=d=>new Intl.DateTimeFormat("fr-CH",{timeZone:"Europe/Zurich",weekday:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(d));
const day=()=>new Intl.DateTimeFormat("sv-SE",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const thresholds={points:[9.5,14.5,19.5,24.5,29.5],rebounds:[2.5,4.5,6.5,8.5,10.5],assists:[1.5,3.5,5.5,7.5,9.5],threes:[0.5,1.5,2.5,3.5,4.5],twos:[0.5,1.5,2.5,3.5,4.5]};
const names={points:"Points",rebounds:"Rebonds",assists:"Passes",threes:"3 paniers",twos:"2 paniers",steals:"Interceptions",blocks:"Contres",minutes:"Minutes"};
const unit={points:"points",rebounds:"rebonds",assists:"passes",threes:"3 points",twos:"2 points",steals:"interceptions",blocks:"contres"};
function tab(name){document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("active",x.dataset.tab===name));document.querySelectorAll(".panel").forEach(x=>x.classList.toggle("active",x.id==="panel-"+name))}
function status(text){$("status").textContent=text}
function save(){localStorage.setItem("nba-radar",JSON.stringify({picks:s.picks,odds:s.odds,stake:$("stake").value}))}
function load(){try{const d=JSON.parse(localStorage.getItem("nba-radar")||"{}");s.picks=d.picks||[];s.odds=d.odds||{};if(d.stake)$("stake").value=d.stake}catch{}}
async function games(date){s.date=date;$("date").value=date;status("Chargement du calendrier NBA…");try{const r=await fetch("/api/games?date="+date),d=await r.json();if(!r.ok)throw Error(d.error||r.status);s.games=d.games||[];$("game-count").textContent=s.games.length;status(s.games.length+" rencontres NBA · "+date+" · Données ESPN");$("games").innerHTML=s.games.map(g=>'<article class="game"><div class="muted">'+esc(local(g.date))+' · '+esc(g.state==="post"?"Terminé":g.state==="in"?"En direct":"À venir")+'</div><h4>'+esc(g.away.name)+' <span>VS</span> '+esc(g.home.name)+'</h4><button class="primary" data-game="'+esc(g.id)+'">Analyser ce match</button></article>').join("")||'<p class="muted">Aucun match ce jour. Choisis une autre date.</p>'; }catch(e){status("Erreur de calendrier : "+e.message)}}
async function analyze(id){
 const g=s.games.find(x=>x.id===id);if(!g)return;
 s.selected=id;tab("joueurs");$("selected-title").textContent=g.away.abbr+" - "+g.home.abbr;$("match-analysis").textContent="Chargement des deux effectifs et des historiques NBA…";
 try{const r=await fetch("/api/report?id="+encodeURIComponent(id)+"&date="+encodeURIComponent(s.date)),d=await r.json();if(!r.ok)throw Error(d.error||r.status);s.report=d;
 if(g.state==="pre"&&Date.parse(g.date)>Date.now()){try{const key="nba_prediction_"+g.id;if(!localStorage.getItem(key))localStorage.setItem(key,JSON.stringify({at:new Date().toISOString(),report:d}))}catch(e){}}
 const model=d.teamProjection.model;
 $("match-analysis").innerHTML=model?'<div class="projection"><div><small>VICTOIRE '+esc(g.away.abbr)+'</small><strong>'+model.awayWinPct+' %</strong></div><div><small>VICTOIRE '+esc(g.home.abbr)+'</small><strong>'+model.homeWinPct+' %</strong></div><div><small>POINTS '+esc(g.away.abbr)+'</small><strong>'+model.awayScore+'</strong></div><div><small>POINTS '+esc(g.home.abbr)+'</small><strong>'+model.homeScore+'</strong></div><div><small>TOTAL ESTIMÉ</small><strong>'+model.total+'</strong></div></div><p class="muted">Estimation simple non calibrée · '+esc(d.lineupStatus)+' · '+esc(model.method)+'</p>':'<p class="muted">Historique d’équipe insuffisant pour projeter le score.</p>';
 if(d.starters?.length){
  $("match-analysis").innerHTML+='<div class="starters"><h4>🏀 Cinq titulaires annoncés par ESPN</h4>'+d.starters.map(t=>'<div><b>'+esc(t.team)+'</b> : '+t.players.map(esc).join(", ")+'</div>').join("")+'</div>';
 }else{
  $("match-analysis").innerHTML+='<p class="muted">Cinq titulaires non confirmés ; actualisation à la prochaine consultation.</p>';
 }
 if(d.retrospective)$("match-analysis").innerHTML+='<p class="warning">Analyse rétrospective reconstruite avec les matchs précédents, pas une prédiction archivée avant rencontre.</p>';
 displayAudit(d);
 $("player-count").textContent=d.players.length;renderPlayers();
 }catch(e){$("match-analysis").textContent="Données indisponibles : "+e.message}
}

function displayAudit(report){
 const output=$("audit");if(!output)return;
 const actual=report.actuals||[];
 if(!report.game.completed||!actual.length){output.innerHTML="";return}
 let snapshot;
 try{snapshot=JSON.parse(localStorage.getItem("nba_prediction_"+report.game.id)||"null")}catch(e){}
 const original=snapshot?.report&&snapshot.at&&Date.parse(snapshot.at)<Date.parse(report.game.date)?snapshot.report:report;
 const points=new Map((original.players||[]).map(p=>[p.id,p]));
 const items=actual.map(x=>({real:x,pred:points.get(x.id)})).filter(x=>x.pred?.projection?.points!=null);
 const mae=(name)=>{
  const matched=items.filter(x=>x.real[name]!=null&&x.pred.projection[name]!=null);
  if(!matched.length)return "—";
  return (matched.reduce((t,x)=>t+Math.abs(x.real[name]-x.pred.projection[name]),0)/matched.length).toFixed(2);
 };
 const hist=original===report;
 const rows=items.sort((a,b)=>(b.pred.projection.points||0)-(a.pred.projection.points||0)).map(x=>{
  const p=x.pred.projection,r=x.real;
  const cell=key=>p[key]==null||r[key]==null?"—":p[key].toFixed(1)+" / "+r[key];
  return '<tr><td>'+esc(x.real.name)+'</td><td>'+cell("points")+'</td><td>'+cell("rebounds")+'</td><td>'+cell("assists")+'</td></tr>'
 }).join("");
 output.innerHTML='<div class="audit"><h3>📋 Audit après match</h3><p class="muted">'+
   (hist?'⚠️ Reconstitution effectuée après la rencontre, sans les chiffres de ce match. Ce ne sont PAS des prédictions archivées avant coup d’envoi.':
   '✓ Comparaison avec la projection enregistrée sur cet iPhone AVANT le début du match ('+esc(new Date(snapshot.at).toLocaleString("fr-CH"))+').')+
   '</p><div class="audit-metrics"><div><small>Erreur moyenne points</small><b>'+mae("points")+'</b></div><div><small>Erreur rebonds</small><b>'+mae("rebounds")+'</b></div><div><small>Erreur passes</small><b>'+mae("assists")+'</b></div></div><div class="audit-scroll"><table><thead><tr><th>Joueur</th><th>PTS prévu/réel</th><th>REB prévu/réel</th><th>AST prévu/réel</th></tr></thead><tbody>'+rows+'</tbody></table></div><p class="muted">Écart absolu moyen sur les joueurs comparables uniquement · les performances non disponibles sont exclues.</p></div>';
}
function renderPlayers(){
 const stat=$("stat-filter").value,q=$("search").value.toLowerCase(),d=s.report;
 if(!d)return;$("player-list").innerHTML=d.players.filter(p=>(p.name+" "+p.team).toLowerCase().includes(q))
 .sort((a,b)=>(b.projection[stat]??0)-(a.projection[stat]??0)).map(p=>{
  const v=p.projection[stat],n=p.games;
  const caution=n<5?" · ⚠️ Petit échantillon":"";
  return '<article class="player"><div><b>'+esc(p.name)+'</b><small>'+esc(p.team)+' · '+n+' matchs'+caution+' · '+esc(p.position||"")+'</small></div><div class="estimate">'+(v==null?"—":v.toFixed(1))+'<small>'+esc(names[stat])+' attendus</small></div><button class="sub" data-player="'+esc(p.id)+'" '+(v==null||d.game.state!=='pre'||Date.parse(d.game.date)<=Date.now()?'disabled':'')+'>＋</button></article>';
 }).join("")||'<p class="muted">Aucun historique sur ce filtre.</p>';
}
function addPick(pid){
 const p=s.report?.players.find(x=>x.id===pid);if(!p)return;
 if(s.picks.length>=10)return alert("Maximum 10 sélections.");
 const stat=$("stat-filter").value,avg=p.projection[stat];
 const threshold=prompt("Seuil bookmaker pour "+p.name+" — "+unit[stat]+" (exemple : 19.5 pour au moins 20 points)",String(Math.max(.5,Math.floor(avg)-.5)));
 if(threshold===null)return;
 const t=Number(threshold);
 if(!Number.isFinite(t)||t<0)return alert("Seuil invalide.");
 const match=s.report.game;
 if(match.state!=="pre"||Date.parse(match.date)<=Date.now())return alert("Match commencé : impossible de sélectionner un marché NBA.");
 s.picks.push({id:pid+"-"+stat+"-"+match.id,matchId:match.id,name:p.name,team:p.team,stat,threshold:t,avg});
 s.odds={};save();renderCoupon();tab("coupons");
}

async function generateCouponNBA(){
 const btn=$("auto-generate"),msg=$("auto-feedback");
 const mode=$("auto-mode").value,n=Number($("auto-count").value),stat=$("auto-stat").value,max=Number($("auto-games").value);
 const selected=s.games.filter(g=>g.state==="pre"&&Date.parse(g.date)>Date.now()).slice(0,max);
 if(!selected.length){msg.textContent="Aucune rencontre NBA non commencée pour cette date. Choisis un autre jour dans Matchs.";return}
 btn.disabled=true;btn.textContent="Analyse des statistiques…";
 const candidates=[],unavailable=[];
 try{
  for(let i=0;i<selected.length;i++){
   const g=selected[i];msg.textContent="Analyse "+(i+1)+"/"+selected.length+" : "+g.away.abbr+" – "+g.home.abbr;
   let d;
   try{
    if(s.report?.game.id===g.id)d=s.report;
    else{const r=await fetch("/api/report?id="+encodeURIComponent(g.id)+"&date="+encodeURIComponent(s.date));d=await r.json();if(!r.ok)throw Error(d.error||r.status)}
   }catch(e){unavailable.push(g.away.abbr+"–"+g.home.abbr);continue}
   for(const p of d.players||[]){
    if(p.sample<5)continue;
    for(const key of stat==="all"?["points","rebounds","assists","threes","twos"]:[stat]){
     const history=(p.history?.[key]||[]).filter(Number.isFinite);
     if(history.length<(mode==="prudent"?7:5)||!Number.isFinite(p.projection?.[key]))continue;
     for(const line of thresholds[key]||[]){
      const hits=history.filter(x=>x>line).length,rate=hits/history.length;
      const acceptable=mode==="prudent"?rate>=.8:mode==="equilibre"?rate>=.6&&rate<.8:rate>=.45&&rate<.6;
      if(!acceptable||p.projection[key]<line-.5)continue;
      candidates.push({id:p.id+"-"+key+"-"+g.id,playerId:p.id,matchId:g.id,name:p.name,team:p.team,stat:key,threshold:line,
         avg:p.projection[key],hits,total:history.length,rate});
     }
    }
   }
  }
  candidates.sort((a,b)=>b.rate-a.rate||b.threshold-a.threshold);
  const picks=[],seen=new Set(),gameCounts={};
  for(const c of candidates){
   if(seen.has(c.playerId)||(gameCounts[c.matchId]||0)>=2)continue;
   picks.push(c);seen.add(c.playerId);gameCounts[c.matchId]=(gameCounts[c.matchId]||0)+1;
   if(picks.length===n)break;
  }
  if(!picks.length){msg.textContent="Aucune sélection satisfaisant ce niveau de régularité. Aucun joueur n'est ajouté artificiellement.";return}
  s.picks=picks;s.odds={};save();renderCoupon();
  msg.textContent=picks.length+"/"+n+" sélections sur statistiques antérieures au match. "+
    (unavailable.length?"Rencontres indisponibles : "+unavailable.join(", ")+". ":"")+
    "Fréquences observées, pas probabilités de gain. Vérifie les compositions et absences.";
 }finally{btn.disabled=false;btn.textContent="🏀 Générer le coupon NBA"}
}
function groups(){let out=new Map();s.picks.forEach(p=>{if(!out.has(p.matchId))out.set(p.matchId,[]);out.get(p.matchId).push(p)});return [...out].map(([id,items])=>({id,items}))}
function renderCoupon(){
 $("pick-count").textContent=s.picks.length;
 $("picks").innerHTML=s.picks.map((p,i)=>'<div class="pick"><div><b>'+esc(p.name)+' · '+esc(names[p.stat])+' > '+p.threshold+'</b><small>Projection : '+p.avg.toFixed(1)+' · '+esc(p.team)+(p.total?' · '+p.hits+'/'+p.total+' derniers matchs au-dessus du seuil':'')+'</small></div><button class="sub" data-remove="'+i+'">✕</button></div>').join("")||'<p class="muted">Aucune sélection pour le moment.</p>';
 $("odds").innerHTML=groups().map(g=>'<div class="odd"><label><b>'+(g.items.length>1?'Pari personnalisé + ('+g.items.length+')':'Cote individuelle')+'</b><input type="number" min="1.01" step=".01" data-odd="'+g.id+'" placeholder="Cote réelle" value="'+esc(s.odds[g.id]||"")+'"></label></div>').join("");
 calculate();
}
function calculate(){const gs=groups(),stake=Number($("stake").value)||0;let product=1,valid=gs.length>0;gs.forEach(g=>{let n=Number(s.odds[g.id]);if(!(n>1))valid=false;else product*=n});$("total-odds").textContent=valid?product.toFixed(2):"—";$("payout").textContent=valid?(stake*product).toFixed(2)+" CHF":"—";$("profit").textContent=valid?(stake*(product-1)).toFixed(2)+" CHF":"—"}
function copy(){const text=["NBA Radar — coupon",...s.picks.map(p=>p.name+" "+names[p.stat]+" > "+p.threshold),...groups().map(g=>"Match "+g.id+" : cote "+(s.odds[g.id]||"à saisir"))].join("\n");if(navigator.clipboard)navigator.clipboard.writeText(text).then(()=>alert("Copié"));else prompt("Copier :",text)}
document.addEventListener("DOMContentLoaded",()=>{
 load();renderCoupon();const date=day();games(date);
 document.querySelectorAll("nav button").forEach(b=>b.addEventListener("click",()=>tab(b.dataset.tab)));
 $("date").addEventListener("change",e=>games(e.target.value));
 $("stat-filter").addEventListener("change",renderPlayers);$("search").addEventListener("input",renderPlayers);
 $("reload").addEventListener("click",()=>s.selected&&analyze(s.selected));
 $("auto-generate").addEventListener("click",generateCouponNBA);
 $("clear").addEventListener("click",()=>{s.picks=[];s.odds={};save();renderCoupon()});
 $("copy").addEventListener("click",copy);
 $("stake").addEventListener("input",()=>{save();calculate()});
 $("odds").addEventListener("input",e=>{if(e.target.dataset.odd){s.odds[e.target.dataset.odd]=e.target.value;save();calculate()}});
 document.addEventListener("click",e=>{let a=e.target.closest("[data-game]");if(a){analyze(a.dataset.game);return}let b=e.target.closest("[data-player]");if(b){addPick(b.dataset.player);return}let c=e.target.closest("[data-remove]");if(c){s.picks.splice(+c.dataset.remove,1);s.odds={};save();renderCoupon()}});
 setInterval(()=>{if(!document.hidden&&s.date)games(s.date)},5*60*1000);
 setInterval(()=>{if(!document.hidden&&s.selected)analyze(s.selected)},5*60*1000);
});
