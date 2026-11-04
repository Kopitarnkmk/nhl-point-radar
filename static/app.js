"use strict";
const $ = id => document.getElementById(id);
const state = {players:[],games:[],picks:[],odds:{},variants:[],date:"",season:"",updated:"",errors:[]};
const dayNY = () => new Intl.DateTimeFormat("sv-SE",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = v => v == null ? "—" : Number(v).toFixed(0)+"%";
const oddText = v => Number(v).toFixed(2);
const fmt = v => Number(v).toLocaleString("fr-CH",{minimumFractionDigits:2,maximumFractionDigits:2})+" CHF";
function getSaved(){
  try {const d=JSON.parse(localStorage.getItem("nhl-radar-v2")||"{}");
    state.picks=Array.isArray(d.picks)?d.picks.filter(x=>Number.isFinite(+x.id)).slice(0,8):[];
    state.odds=d.odds&&typeof d.odds==="object"?d.odds:{};
    if(Number.isFinite(+d.stake) && +d.stake>=0)$("stake").value=d.stake;
  }catch(e){state.picks=[];state.odds={}}
}
function save(){try{localStorage.setItem("nhl-radar-v2",JSON.stringify({picks:state.picks,odds:state.odds,stake:$("stake").value}))}catch(e){}}
function setNotice(text,error=false){const n=$("notice");n.textContent=text;n.className="notice "+(error?"error":"ok")}
function tab(name){document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("active",x.dataset.tab===name));document.querySelectorAll(".panel").forEach(x=>x.classList.toggle("active",x.id==="panel-"+name));if(name==="coupons")renderCoupon();window.scrollTo({top:Math.min(window.scrollY,270),behavior:"smooth"})}
function selected(id){return state.picks.some(p=>p.id===id)}
function byId(id){return state.players.find(p=>p.id===id)}
function playerCard(p){
  return '<div class="player-card"><div class="person"><div class="person-name">'+esc(p.name)+'</div><div class="person-meta">'+esc(p.team)+' · '+esc(p.position)+' · <span class="badge">'+esc(p.profile)+'</span></div></div>'+
  '<div class="cell"><small>SAISON 1+ PT</small><strong>'+esc(p.pointGames)+'/'+esc(p.games)+' ('+pct(p.seasonRate)+')</strong></div>'+
  '<div class="cell"><small>10 DERNIERS</small><strong class="mint">'+esc(p.last10.withPoint)+'/'+esc(p.last10.matches)+'</strong></div>'+
  '<div class="cell"><small>BUTS / PASSES</small><strong>'+esc(p.goals)+' / '+esc(p.assists)+'</strong></div>'+
  '<div class="cell"><small>INDICE</small><strong>'+esc(p.index)+'</strong></div>'+
  '<div class="actions"><button class="mini" data-info="'+p.id+'" aria-label="Détail du joueur">ⓘ</button><button class="mini '+(selected(p.id)?"remove":"add")+'" data-add="'+p.id+'" aria-label="'+(selected(p.id)?"Retirer":"Ajouter")+' le joueur">'+(selected(p.id)?"−":"＋")+'</button></div></div>';
}
function listTop(){
  const q=$("search").value.trim().toLowerCase(),profile=$("profile").value,sort=$("sort").value;
  const data=state.players.filter(p=>(!q||(p.name+" "+p.team).toLowerCase().includes(q))&&(!profile||p.profile===profile)).slice();
  const val=p=>sort==="points"?p.points:sort==="season"?p.seasonRate:sort==="last10"?p.last10.rate:p.index;
  data.sort((a,b)=>(val(b)||0)-(val(a)||0)||b.points-a.points);
  $("player-list").classList.toggle("empty",data.length===0);
  $("player-list").innerHTML=data.length?data.slice(0,130).map(playerCard).join(""):"Aucun joueur trouvé.";
}
function listForm(){
  const w=$("forme-window").value,profile=$("forme-profile").value;
  const data=state.players.filter(p=>(!profile||p.profile===profile)&&p[w].matches>=5).slice().sort((a,b)=>(b[w].rate||0)-(a[w].rate||0)||b.index-a.index);
  $("form-list").classList.toggle("empty",data.length===0);
  $("form-list").innerHTML=data.length?data.slice(0,80).map(playerCard).join(""):"Aucune donnée pour ce filtre.";
}
function openPlayer(id){
  const p=byId(id);if(!p)return;
  $("dialog-name").textContent=p.name;
  const rows=(p.recentGames||[]).slice().reverse().map(g=>'<tr><td>'+esc(g.date)+'</td><td>'+esc(g.opponent)+'</td><td>'+g.goals+'</td><td>'+g.assists+'</td><td style="color:'+(g.points>0?"#20e8b5":"#a2b5bd")+'">'+g.points+'</td></tr>').join("");
  $("dialog-detail").innerHTML='<p>'+esc(p.team)+' · '+esc(p.profile)+' · '+p.goals+' buts · '+p.assists+' passes</p><div class="metrics"><div class="metric"><div class="metric-lbl">SAISON</div><div class="metric-val">'+pct(p.seasonRate)+'</div></div><div class="metric"><div class="metric-lbl">10 MATCHS</div><div class="metric-val">'+pct(p.last10.rate)+'</div></div><div class="metric"><div class="metric-lbl">5 MATCHS</div><div class="metric-val">'+pct(p.last5.rate)+'</div></div></div><table class="history"><thead><tr><th>Date</th><th>Adv.</th><th>B</th><th>A</th><th>Pts</th></tr></thead><tbody>'+rows+'</tbody></table><p class="hint">Matchs terminés uniquement. Historique du plus récent au plus ancien.</p>';
  $("player-dialog").showModal();
}
function addPick(id){
  const p=byId(id);if(!p)return;
  if(selected(id))state.picks=state.picks.filter(x=>x.id!==id);
  else {if(state.picks.length>=8){alert("Maximum 8 sélections par coupon.");return}
    const game=gameForTeam(p.team);
    state.picks.push({id:p.id,gameId:game?game.id:null,gameLabel:game?game.away+" - "+game.home:""});
  }
  save();renderAll();
}
function gameForTeam(team){if(!team||team.includes(",")||team.includes(" "))return null;return state.games.find(g=>g.away===team||g.home===team)||null}
function upcoming(g){return ["FUT","PRE"].includes(g.state)&&Date.parse(g.startUTC)>Date.now()}
function timeLocal(iso){if(!iso)return"Horaire à confirmer";try{return new Intl.DateTimeFormat("fr-CH",{weekday:"short",hour:"2-digit",minute:"2-digit",timeZone:"Europe/Zurich"}).format(new Date(iso))}catch(e){return iso}}
function matchView(){
  $("kpi-games").textContent=state.games.length;
  const html=state.games.map(g=>{
    const future=upcoming(g);
    const players=state.players.filter(p=>p.team===g.away||p.team===g.home).sort((a,b)=>b.index-a.index).slice(0,6);
    const chips=players.map(p=>'<button class="chip" data-add="'+p.id+'">'+esc(p.name.split(" ").slice(-1)[0])+' ＋</button>').join("");
    return '<div class="game-card"><div class="game-top"><span class="game-meta">'+esc(timeLocal(g.startUTC))+'</span><span class="state '+(future?"":"started")+'">'+(future?"À venir":g.state==="OFF"||g.state==="FINAL"?"Terminé":"En cours / commencé")+'</span></div>'+
    '<div class="game-teams"><span>'+esc(g.away)+'</span><span class="game-versus">'+(g.awayScore!=null?esc(g.awayScore)+" – "+esc(g.homeScore):"VS")+'</span><span>'+esc(g.home)+'</span></div>'+
    '<div class="game-pick-title">'+(future?"Joueurs à suivre":"Match non disponible pour les nouvelles suggestions")+'</div>'+
    (future?'<div class="game-options">'+(chips||'<small>Pas de joueur analysé pour ce match.</small>')+'</div>':'')+'</div>';
  }).join("");
  $("game-list").classList.toggle("empty",!state.games.length);
  $("game-list").innerHTML=html||"Aucun match NHL sur cette journée.";
}
function makeGroups(){
  const map=new Map();
  state.picks.forEach(k=>{
    const p=byId(k.id);if(!p)return;
    const game=state.games.find(g=>g.away===p.team||g.home===p.team);
    const key=game?"game:"+game.id:"solo:"+p.id;
    if(!map.has(key))map.set(key,{key,label:game?game.away+" – "+game.home:p.team,players:[],game:game||null});
    map.get(key).players.push(p);
  });
  return Array.from(map.values());
}
function renderCoupon(){
  $("kpi-picks").textContent=state.picks.length;
  $("tab-count").textContent=state.picks.length;
  $("selected-count").textContent=state.picks.length+" sélection"+(state.picks.length>1?"s":"");
  const entries=state.picks.map(s=>byId(s.id)).filter(Boolean);
  const rows=entries.map(p=>'<div class="coupon-row"><div><b>'+esc(p.name)+'</b><div class="sub">'+esc(p.team)+' · 1+ point · 10 derniers '+p.last10.withPoint+'/'+p.last10.matches+'</div></div><button class="mini remove" data-add="'+p.id+'" aria-label="Retirer">✕</button></div>').join("");
  $("coupon-picks").classList.toggle("empty",!entries.length);
  $("coupon-picks").innerHTML=rows||"Ajoute un joueur depuis Top joueurs, Forme ou Matchs.";
  const groups=makeGroups();
  $("odds-area").innerHTML=groups.map((g,i)=>'<div class="group-row"><label><b>'+(g.players.length>1?'Pari personnalisé + ('+g.players.length+' joueurs)':'Cote individuelle')+'</b><br>'+esc(g.label)+'<br>'+esc(g.players.map(p=>p.name).join(" + "))+'<input class="odd-input" data-key="'+esc(g.key)+'" type="number" inputmode="decimal" min="1.01" step=".01" placeholder="Cote bookmaker (ex. 1.45)" value="'+(Number(state.odds[g.key])>1?esc(state.odds[g.key]):"")+'"></label></div>').join("");
  updateReturn();
}
function updateReturn(){
  const groups=makeGroups(),stake=Math.max(0,Number($("stake").value)||0);
  let total=1,valid=groups.length>0;
  for(const g of groups){const o=Number(state.odds[g.key]);if(!(o>1&&Number.isFinite(o))){valid=false;break}total*=o}
  $("total-odds").textContent=valid?oddText(total):"—";
  $("return").textContent=valid?fmt(stake*total):"—";
  $("profit").textContent=valid?fmt(stake*(total-1)):"—";
  $("odds-note").textContent=valid?"Calcul théorique selon les cotes saisies. Aucune sélection n'est garantie.":groups.length?"Renseigne toutes les cotes de ton bookmaker, y compris la cote unique du Pari personnalisé + si plusieurs joueurs partagent un match.":"Aucune cote estimée ou inventée par l'application.";
}
function modePass(p,mode){
  const r10=p.last10.rate||0, season=p.seasonRate||0, r5=p.last5.rate||0;
  if(mode==="prudent")return r10>=80 && season>=72;
  if(mode==="equilibre")return r10>=70 && r10<90 && season>=60;
  return r10>=40 && r10<70 && r5>=60 && season>=50 && (p.points/Math.max(1,p.games))>=.7;
}
function candidateScore(p,mode){
  const r10=p.last10.rate||0, season=p.seasonRate||0, r5=p.last5.rate||0;
  if(mode==="prudent")return .55*r10+.35*season+.1*p.index;
  if(mode==="exploratoire")return .6*r5+.25*Math.min(100,p.points/Math.max(1,p.games)*50)+.15*p.index;
  return .35*r10+.4*r5+.25*season+(p.profile==="Polyvalent"?4:0);
}
function suggest(mode,n,allowPairs){
  const games=state.games.filter(upcoming);
  if(!games.length)return {picks:[],reason:"Aucun match non commencé sur la date sélectionnée."};
  const teams=new Set(games.flatMap(g=>[g.away,g.home]));
  const base=state.players.filter(p=>teams.has(p.team)&&p.games>=10&&p.last10.matches>=10);
  // Les trois modes occupent des bandes historiques distinctes ; aucun n'est « garanti ».
  const players=base.filter(p=>modePass(p,mode)).sort((a,b)=>candidateScore(b,mode)-candidateScore(a,mode));
  const chosen=[],perGame=new Map();
  for(const p of players){
    const g=gameForTeam(p.team);if(!g||!upcoming(g))continue;
    if((perGame.get(g.id)||0)>=(allowPairs?2:1))continue;
    chosen.push({id:p.id,gameId:g.id,gameLabel:g.away+" - "+g.home});
    perGame.set(g.id,(perGame.get(g.id)||0)+1);
    if(chosen.length>=n)break;
  }
  const why=mode==="prudent"?"Prudent : 8+/10 et saison ≥72 %."
            :mode==="equilibre"?"Équilibré : 7–8/10 et saison ≥60 %."
            :"Exploratoire : 4–6/10, accélération récente, saison ≥50 %.";
  return {picks:chosen,reason:why+" "+(chosen.length<n?"Seulement "+chosen.length+" joueur(s) admissible(s) pour "+n+" demandé(s). Aucun joueur ajouté artificiellement.":"Ces groupes ne représentent pas des cotes ni des probabilités calculées.")};
}
async function loadGames(day){
  state.date=day;$("game-day").value=day;$("builder-date").value=day;
  try{const r=await fetch("/api/games?date="+encodeURIComponent(day));const d=await r.json();if(!r.ok)throw Error(d.error||r.status);
    if(state.date!==day)return;
    state.games=d.games||[];matchView();renderCoupon();if(d.stale)setNotice(d.warning||"Calendrier en cache.",true);
  }catch(e){state.games=[];matchView();renderCoupon();setNotice("Calendrier indisponible : "+e.message,true)}
}
async function loadPlayers(){
  try{const r=await fetch("/api/players");const d=await r.json();if(!r.ok)throw Error(d.error||r.status);
    state.players=d.players||[];state.season=d.season||"";state.updated=d.updatedAt||"";
    $("season-badge").textContent=state.season?state.season.slice(0,4)+"/"+state.season.slice(4):"SAISON";
    $("kpi-players").textContent=state.players.length;
    $("update-top").textContent=state.updated?"NHL · "+timeLocal(state.updated):"";
    $("footer-updated").textContent=state.updated?"Dernier relevé : "+new Date(state.updated).toLocaleString("fr-CH"):"";
    setNotice(d.stale?d.warning||"Dernières données conservées.":state.players.length+" joueurs analysés · Données NHL mises à jour. "+(d.partial?"Certains historiques sont manquants.":""),Boolean(d.stale));
    renderAll();
  }catch(e){setNotice("Statistiques NHL indisponibles : "+e.message,true);$("player-list").textContent="Impossible de charger les joueurs. Réessaie plus tard."; $("form-list").textContent="Données indisponibles."}
}
function renderAll(){listTop();listForm();matchView();renderCoupon()}
function showVariants(){
  const names=[["prudent",3,"Prudent"],["equilibre",4,"Équilibré"],["exploratoire",6,"Exploratoire"]];
  state.variants=names.map(row=>{const found=suggest(row[0],row[1],false);return {mode:row[0],name:row[2],picks:found.picks,reason:found.reason}});
  $("variants").innerHTML=state.variants.map((v,i)=>'<div class="variant-card"><h4>'+esc(v.name)+' · '+v.picks.length+' joueurs</h4><div class="small">'+(v.picks.map(p=>{const pl=byId(p.id);return pl?esc(pl.name):""}).join(" · ")||esc(v.reason))+'</div><button class="secondary" data-variant="'+i+'" '+(v.picks.length?"":"disabled")+'>Utiliser ce coupon</button></div>').join("");
  $("builder-message").textContent="Ce sont des suggestions statistiques, pas des probabilités de réussite. Les cotes restent à saisir manuellement.";
}
function generate(){
  const n=Number($("pick-count").value),mode=$("mode").value,pair=$("pair-mode").value==="allow";
  const res=suggest(mode,n,pair);
  if(!res.picks.length){$("builder-message").textContent=res.reason;return}
  state.picks=res.picks;state.odds={};save();renderAll();$("builder-message").textContent=res.reason||"Coupon proposé : "+res.picks.length+" joueurs. Vérifie les compositions, blessures et cotes avant toute décision.";
}
function copyCoupon(){
  const picks=state.picks.map(s=>byId(s.id)).filter(Boolean),groups=makeGroups();
  if(!picks.length){alert("Coupon vide.");return}
  const all=groups.every(g=>Number(state.odds[g.key])>1);
  const total=all?groups.reduce((x,g)=>x*Number(state.odds[g.key]),1):null;
  const lines=["NHL POINT RADAR — COUPON 1+ POINT",state.date,"",...picks.map(p=>"- "+p.name+" ("+p.team+") : 1+ point"),"",...groups.map(g=>g.label+" : "+(Number(state.odds[g.key])>1?oddText(state.odds[g.key]):"cote à saisir")),"",total?"Cote totale : "+oddText(total):"Cotes à compléter","Mise : "+$("stake").value+" CHF","Outil statistique, aucune garantie."];
  const str=lines.join("\n");
  if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(str).then(()=>alert("Coupon copié !")).catch(()=>prompt("Copier le coupon :",str));
  else prompt("Copier le coupon :",str);
}
function init(){
  getSaved();const today=dayNY();state.date=today;$("game-day").value=today;$("builder-date").value=today;
  document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click",()=>tab(b.dataset.tab)));
  ["search","profile","sort"].forEach(id=>$(id).addEventListener("input",listTop));
  ["forme-window","forme-profile"].forEach(id=>$(id).addEventListener("change",listForm));
  $("game-day").addEventListener("change",e=>loadGames(e.target.value));
  $("builder-date").addEventListener("change",e=>loadGames(e.target.value));
  $("generate").addEventListener("click",generate);
  $("trio").addEventListener("click",showVariants);
  $("clear").addEventListener("click",()=>{state.picks=[];state.odds={};save();renderAll()});
  $("stake").addEventListener("input",()=>{save();updateReturn()});
  $("copy-coupon").addEventListener("click",copyCoupon);
  $("reload").addEventListener("click",()=>{setNotice("Actualisation en cours…");loadPlayers();loadGames(state.date)});
  $("dialog-close").addEventListener("click",()=>$("player-dialog").close());
  $("odds-area").addEventListener("input",e=>{const k=e.target.dataset.key;if(!k)return;state.odds[k]=e.target.value;save();updateReturn()});
  document.addEventListener("click",e=>{
    const a=e.target.closest("[data-add]");if(a){addPick(Number(a.dataset.add));return}
    const b=e.target.closest("[data-info]");if(b){openPlayer(Number(b.dataset.info));return}
    const c=e.target.closest("[data-variant]");if(c){const v=state.variants[Number(c.dataset.variant)];if(!v)return;state.picks=v.picks;state.odds={};save();renderAll();tab("coupons");return}
  });
  loadGames(today);loadPlayers();
  setInterval(()=>{if(!document.hidden){loadGames(state.date);loadPlayers()}},15*60*1000);
}
document.addEventListener("DOMContentLoaded",init);
