"use strict";
const $=id=>document.getElementById(id),s={date:"",games:[],report:null,selected:null,picks:[],odds:{}};
const esc=v=>String(v??"").replace(/[&<>"']/g,k=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[k]));
const local=d=>new Intl.DateTimeFormat("fr-CH",{timeZone:"Europe/Zurich",weekday:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(d));
const day=()=>new Intl.DateTimeFormat("sv-SE",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
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
 const model=d.teamProjection.model;
 $("match-analysis").innerHTML=model?'<div class="projection"><div><small>VICTOIRE '+esc(g.away.abbr)+'</small><strong>'+model.awayWinPct+' %</strong></div><div><small>VICTOIRE '+esc(g.home.abbr)+'</small><strong>'+model.homeWinPct+' %</strong></div><div><small>POINTS '+esc(g.away.abbr)+'</small><strong>'+model.awayScore+'</strong></div><div><small>POINTS '+esc(g.home.abbr)+'</small><strong>'+model.homeScore+'</strong></div><div><small>TOTAL ESTIMÉ</small><strong>'+model.total+'</strong></div></div><p class="muted">Estimation simple non calibrée · '+esc(d.lineupStatus)+' · '+esc(model.method)+'</p>':'<p class="muted">Historique d’équipe insuffisant pour projeter le score.</p>';
 $("player-count").textContent=d.players.length;renderPlayers();
 }catch(e){$("match-analysis").textContent="Données indisponibles : "+e.message}
}
function renderPlayers(){
 const stat=$("stat-filter").value,q=$("search").value.toLowerCase(),d=s.report;
 if(!d)return;$("player-list").innerHTML=d.players.filter(p=>(p.name+" "+p.team).toLowerCase().includes(q))
 .sort((a,b)=>(b.projection[stat]??0)-(a.projection[stat]??0)).map(p=>{
  const v=p.projection[stat],n=p.games;
  return '<article class="player"><div><b>'+esc(p.name)+'</b><small>'+esc(p.team)+' · '+n+' matchs · '+esc(p.position||"")+'</small></div><div class="estimate">'+(v==null?"—":v.toFixed(1))+'<small>'+esc(names[stat])+' attendus</small></div><button class="sub" data-player="'+esc(p.id)+'" '+(v==null?'disabled':'')+'>＋</button></article>';
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
 s.picks.push({id:pid+"-"+stat+"-"+match.id,matchId:match.id,name:p.name,team:p.team,stat,threshold:t,avg});
 s.odds={};save();renderCoupon();tab("coupons");
}
function groups(){let out=new Map();s.picks.forEach(p=>{if(!out.has(p.matchId))out.set(p.matchId,[]);out.get(p.matchId).push(p)});return [...out].map(([id,items])=>({id,items}))}
function renderCoupon(){
 $("pick-count").textContent=s.picks.length;
 $("picks").innerHTML=s.picks.map((p,i)=>'<div class="pick"><div><b>'+esc(p.name)+' · '+esc(names[p.stat])+' > '+p.threshold+'</b><small>Projection : '+p.avg.toFixed(1)+' · '+esc(p.team)+'</small></div><button class="sub" data-remove="'+i+'">✕</button></div>').join("")||'<p class="muted">Aucune sélection pour le moment.</p>';
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
 $("clear").addEventListener("click",()=>{s.picks=[];s.odds={};save();renderCoupon()});
 $("copy").addEventListener("click",copy);
 $("stake").addEventListener("input",()=>{save();calculate()});
 $("odds").addEventListener("input",e=>{if(e.target.dataset.odd){s.odds[e.target.dataset.odd]=e.target.value;save();calculate()}});
 document.addEventListener("click",e=>{let a=e.target.closest("[data-game]");if(a){analyze(a.dataset.game);return}let b=e.target.closest("[data-player]");if(b){addPick(b.dataset.player);return}let c=e.target.closest("[data-remove]");if(c){s.picks.splice(+c.dataset.remove,1);s.odds={};save();renderCoupon()}});
 setInterval(()=>{if(!document.hidden&&s.date)games(s.date)},5*60*1000);
});
