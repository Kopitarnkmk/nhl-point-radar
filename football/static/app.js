"use strict";
const $=id=>document.getElementById(id);
const esc=x=>String(x==null?"":x).replace(/[&<>"']/g,k=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[k]));
const tzDay=()=>new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Zurich",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const money=x=>Number(x).toLocaleString("fr-CH",{minimumFractionDigits:2,maximumFractionDigits:2})+" CHF";
const state={date:"",competitions:[],fixtures:[],errors:[],histories:{},pending:{},picks:[],odds:{},variants:[],selected:null};
const ALL_MARKETS=[
  {id:"o15",label:"Plus de 1,5 buts",type:"prudent"},
  {id:"home1",label:"Domicile marque 1+ but",type:"prudent"},
  {id:"away1",label:"Extérieur marque 1+ but",type:"prudent"},
  {id:"dc1x",label:"Double chance 1X",type:"prudent"},
  {id:"dcx2",label:"Double chance X2",type:"prudent"},
  {id:"o25",label:"Plus de 2,5 buts",type:"equilibre"},
  {id:"btts",label:"Les deux équipes marquent",type:"equilibre"},
  {id:"homewin",label:"Victoire domicile (90 min)",type:"equilibre"},
  {id:"awaywin",label:"Victoire extérieur (90 min)",type:"exploratoire"},
  {id:"home2",label:"Domicile marque 2+ buts",type:"exploratoire"},
  {id:"away2",label:"Extérieur marque 2+ buts",type:"exploratoire"},
  {id:"o35",label:"Plus de 3,5 buts",type:"exploratoire"},
];
const MARKET=Object.fromEntries(ALL_MARKETS.map(m=>[m.id,m]));
const MODE={
 prudent:{list:["o15","home1","away1","dc1x","dcx2"],minSample:8,minIndex:62,label:"Prudent"},
 equilibre:{list:["o25","btts","homewin","home2","dc1x"],minSample:7,minIndex:53,label:"Équilibré"},
 exploratoire:{list:["o35","home2","away2","awaywin","homewin","btts"],minSample:5,minIndex:37,label:"Exploratoire"}
};
function note(s,error=false){$("notice").textContent=s;$("notice").className="notice "+(error?"error":"ok")}
function localTime(d){try{return new Intl.DateTimeFormat("fr-CH",{timeZone:"Europe/Zurich",hour:"2-digit",minute:"2-digit"}).format(new Date(d))}catch{return "—"}}
function tab(n){document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active",b.dataset.tab===n));document.querySelectorAll(".panel").forEach(p=>p.classList.toggle("active",p.id==="panel-"+n));window.scrollTo({top:270,behavior:"smooth"})}
function readSaved(){try{let d=JSON.parse(localStorage.getItem("football-radar-v1")||"{}");state.picks=Array.isArray(d.picks)?d.picks.slice(0,8):[];state.odds=d.odds||{};if(Number.isFinite(+d.stake))$("stake").value=d.stake;}catch{state.picks=[];state.odds={}}}
function persist(){try{localStorage.setItem("football-radar-v1",JSON.stringify({picks:state.picks,odds:state.odds,stake:$("stake").value}))}catch{}}
function compLabel(f){return esc(f.competitionName||f.competition)}
function renderOptions(){
  const opts=state.competitions.map(c=>'<option value="'+esc(c.id)+'">'+esc(c.name)+'</option>').join("");
  $("comp-filter").innerHTML='<option value="all">Toutes les compétitions</option>'+opts;
  $("builder-comp").innerHTML='<option value="all">Tous les matchs de la date</option>'+
   '<optgroup label="Par catégorie"><option value="championnat">Championnats</option><option value="coupe">Coupes nationales</option><option value="europe">Coupes d’Europe</option></optgroup><optgroup label="Compétition précise">'+opts+'</optgroup>';
}
function visibleFixtures(){
 const kind=$("kind-filter").value,comp=$("comp-filter").value;
 return state.fixtures.filter(f=>(kind==="all"||f.kind===kind)&&(comp==="all"||f.competition===comp));
}
function upcoming(f){return f.state==="pre"&&Date.parse(f.date)>Date.now()}
function statusText(f){if(f.completed)return "Terminé";if(f.state==="in")return "En direct";if(upcoming(f))return "À venir";return f.status||"Déjà commencé"}
function renderFixtures(){
 const fixtures=visibleFixtures(),list=$("match-list");
 $("count-matches").textContent=state.fixtures.length;
 $("count-competitions").textContent=new Set(state.fixtures.map(f=>f.competition)).size;
 $("match-count-label").textContent=fixtures.length+" match"+(fixtures.length>1?"s":"")+" dans le filtre · Calendrier officiel ESPN · Heure suisse";
 list.classList.toggle("empty",fixtures.length===0);
 list.innerHTML=fixtures.map(f=>{
   const score=v=>v==null?"–":esc(v);
   const team=t=>'<div class="teamline"><div class="teamword">'+(t.logo?'<img alt="" loading="lazy" src="'+esc(t.logo)+'">':"")+'<span>'+esc(t.name)+'</span></div><strong>'+score(t.goals)+'</strong></div>';
   return '<article class="match-card"><div class="topline"><span class="comp-badge '+esc(f.kind)+'">'+compLabel(f)+'</span><span class="match-time">'+esc(localTime(f.date))+'</span></div><div class="stagename">'+esc(f.stage||f.country||"")+'</div>'+team(f.home)+team(f.away)+'<div class="bottomline"><span class="status '+(upcoming(f)?"upcoming":"ended")+'">'+esc(statusText(f))+'</span><button class="small-btn" data-analyze="'+esc(f.id)+'">📊 Analyser</button></div></article>'
 }).join("")||(state.errors.length?"Aucune rencontre trouvée dans ce filtre. Certaines compétitions sont temporairement indisponibles.":"Aucune rencontre trouvée dans ce filtre.");
}
async function getHistory(comp){
 if(state.histories[comp])return state.histories[comp];
 if(state.pending[comp])return state.pending[comp];
 state.pending[comp]=(async()=>{
   const response=await fetch("/api/history?competition="+encodeURIComponent(comp));
   const data=await response.json();
   if(!response.ok)throw Error(data.error||"Impossible de récupérer l'historique");
   state.histories[comp]=data;
   return data;
 })();
 try{return await state.pending[comp]}finally{delete state.pending[comp]}
}
function teamMatches(match,teamId){
 const data=state.histories[match.competition];
 if(!data)return [];
 return data.games.filter(g=>{
    if(g.id===match.id)return false;
    if(Date.parse(g.date)>=Date.parse(match.date))return false;
    return g.home.id===teamId||g.away.id===teamId;
 }).sort((a,b)=>Date.parse(a.date)-Date.parse(b.date));
}
function summarize(matches,id,venue=null){
 let m=matches.filter(g=>venue===null||(venue==="home"?g.home.id===id:g.away.id===id)).slice(-10);
 let n=m.length;
 if(!n)return {n:0,rate:{},w:0,d:0,l:0,gf:0,ga:0};
 let counts={o15:0,o25:0,o35:0,btts:0,scored1:0,scored2:0,conceded1:0,conceded2:0,win:0,draw:0,loss:0,notLose:0,notWin:0};
 let gf=0,ga=0;
 m.forEach(g=>{
   const home=g.home.id===id;
   const scored=home?g.home.goals:g.away.goals;
   const conceded=home?g.away.goals:g.home.goals;
   gf+=scored;ga+=conceded;
   const total=scored+conceded;
   if(total>1)counts.o15++;
   if(total>2)counts.o25++;
   if(total>3)counts.o35++;
   if(scored>0&&conceded>0)counts.btts++;
   if(scored>=1)counts.scored1++;
   if(scored>=2)counts.scored2++;
   if(conceded>=1)counts.conceded1++;
   if(conceded>=2)counts.conceded2++;
   if(scored>conceded)counts.win++;
   if(scored===conceded)counts.draw++;
   if(scored<conceded)counts.loss++;
   if(scored>=conceded)counts.notLose++;
   if(scored<=conceded)counts.notWin++;
 });
 return {n,gf,ga,w:counts.win,d:counts.draw,l:counts.loss,rate:Object.fromEntries(Object.entries(counts).map(([k,v])=>[k,Math.round(v*100/n)]))};
}
function stats(match){
 const h=teamMatches(match,match.home.id),a=teamMatches(match,match.away.id);
 return {home:summarize(h,match.home.id),away:summarize(a,match.away.id),
         homeVenue:summarize(h,match.home.id,"home"),awayVenue:summarize(a,match.away.id,"away")};
}
function index(match,market){
 const s=stats(match),h=s.home.rate,a=s.away.rate;
 const formula={
   o15:["o15","o15"],o25:["o25","o25"],o35:["o35","o35"],btts:["btts","btts"],
   home1:["scored1","conceded1"],away1:["conceded1","scored1"],
   home2:["scored2","conceded2"],away2:["conceded2","scored2"],
   dc1x:["notLose","notWin"],dcx2:["notWin","notLose"],
   homewin:["win","loss"],awaywin:["loss","win"]
 }[market];
 if(!formula)return null;
 if(s.home.n<5||s.away.n<5)return null;
 let raw=.5*(h[formula[0]]||0)+.5*(a[formula[1]]||0);
 if(s.homeVenue.n>=4&&s.awayVenue.n>=4){
   const hh=s.homeVenue.rate,aa=s.awayVenue.rate;
   const atVenue=.5*(hh[formula[0]]||0)+.5*(aa[formula[1]]||0);
   raw=.8*raw+.2*atVenue;
 }
 return Math.round(raw);
}
function niceRate(v){return v==null?"—":v+"%"}
function rowStat(key,value){return '<div class="line"><span>'+esc(key)+'</span><b>'+esc(value)+'</b></div>'}
function teamPanel(team,summary,venue,context){
  const r=summary.rate;
  return '<div class="team-stats"><h4>'+esc(team.name)+'</h4><div class="basic"><div><small>MATCHS</small><strong>'+summary.n+'</strong></div><div><small>V / N / D</small><strong style="font-size:15px">'+summary.w+'/'+summary.d+'/'+summary.l+'</strong></div><div><small>BUTS + / -</small><strong style="font-size:15px">'+summary.gf+'/'+summary.ga+'</strong></div></div>'+
  rowStat("Les deux marquent",niceRate(r.btts))+rowStat("Plus de 2,5 buts",niceRate(r.o25))+rowStat("Marque au moins 1 but",niceRate(r.scored1))+rowStat("Marque au moins 2 buts",niceRate(r.scored2))+
  '<p class="caption">'+esc(context)+", "+venue.n+" match(s) de lieu étudié(s).</p></div>"
}
async function analyze(id){
 const f=state.fixtures.find(f=>f.id===String(id));
 if(!f)return;
 state.selected=f;
 tab("analyse");
 $("analysis").className="";
 $("analysis").innerHTML='<div class="notice">Récupération des matchs précédents en '+esc(f.competitionName)+'…</div>';
 try{await getHistory(f.competition); if(state.selected?.id!==f.id)return;renderAnalysis(f)}
 catch(err){$("analysis").innerHTML='<div class="warning">Données ESPN indisponibles : '+esc(err.message)+'</div>'}
}
function renderAnalysis(f){
 const s=stats(f),good=s.home.n>=5&&s.away.n>=5;
 const all=ALL_MARKETS.map(m=>{
   const score=index(f,m.id);
   return '<div class="market-card"><div><b>'+esc(m.label)+'</b><small>'+(score==null?"Échantillon insuffisant":'Convergence historique '+score+'/100')+'</small></div><button class="small-btn" data-market="'+esc(m.id)+'" data-game="'+esc(f.id)+'" '+(upcoming(f)?"":"disabled")+' title="Ajouter au coupon">＋</button></div>'
 }).join("");
 $("analysis").innerHTML='<div class="analysis-info"><div class="analysis-head"><h4>'+esc(f.home.name)+' – '+esc(f.away.name)+'</h4><span class="comp-badge '+esc(f.kind)+'">'+esc(f.competitionName)+'</span></div><p>'+esc(f.stage||"")+" · "+esc(localTime(f.date))+' · '+esc(f.country)+'</p><div class="caption"><b>Référence : uniquement '+esc(f.competitionName)+'</b> · Saison courante · Jusqu’au coup d’envoi du match</div></div>'+
 (!good?'<div class="warning">Échantillon limité : '+s.home.n+' match(s) pour '+esc(f.home.name)+' et '+s.away.n+' pour '+esc(f.away.name)+' dans cette compétition. Les indices automatiques ne sont pas établis sans 5 matchs minimum par équipe.</div>':"")+
 '<div class="analysis-stats">'+teamPanel(f.home,s.home,s.homeVenue,"À domicile")+teamPanel(f.away,s.away,s.awayVenue,"À l’extérieur")+'</div><div class="section-head"><h3>Marchés étudiés</h3></div><p class="caption">L’indice de convergence décrit deux historiques ; <b>ce n’est pas une probabilité de réussite</b>. Les statistiques de prolongations des coupes ne sont pas toujours isolables pour les marchés « 90 min ».</p><div class="market-cards">'+all+'</div>';
}
function key(p){return String(p.eventId)+":"+p.market}
function addPick(eventId,market){
 if(!MARKET[market])return;
 const f=state.fixtures.find(x=>x.id===String(eventId));
 if(!f){alert("Match introuvable sur cette date.");return}
 if(!upcoming(f)){alert("Ce match a déjà commencé : aucune nouvelle sélection.");return}
 const p={eventId:f.id,competition:f.competition,home:f.home.name,away:f.away.name,market};
 const found=state.picks.findIndex(q=>key(q)===key(p));
 if(found>=0){state.picks.splice(found,1)}
 else {if(state.picks.length>=8){alert("Maximum 8 sélections.");return}state.picks.push(p)}
 state.odds={};persist();renderCoupon();
}
function groups(){
 const map=new Map();state.picks.forEach(p=>{
   if(!map.has(p.eventId))map.set(p.eventId,[]);
   map.get(p.eventId).push(p);
 });
 return [...map.entries()].map(([eventId,items])=>({eventId,items,label:items[0].home+" – "+items[0].away}));
}
function oddKey(group){return "event:"+group.eventId}
function renderCoupon(){
 $("count-picks").textContent=state.picks.length;
 $("pick-label").textContent=state.picks.length+" sélection"+(state.picks.length>1?"s":"");
 $("coupon-picks").classList.toggle("empty",state.picks.length===0);
 $("coupon-picks").innerHTML=state.picks.map((p,i)=>{
   const f=state.fixtures.find(f=>f.id===p.eventId);
   return '<div class="pick-item"><div><b>'+esc(MARKET[p.market]?.label||p.market)+'</b><small>'+esc(p.home)+' – '+esc(p.away)+' · '+esc(f?.competitionName||p.competition)+'</small></div><button class="close-btn" data-remove="'+i+'" aria-label="Retirer la sélection">✕</button></div>'
 }).join("")||"Ajoute un marché depuis l’analyse d’un match ou le générateur.";
 $("odds-inputs").innerHTML=groups().map(g=>{
   const odds=state.odds[oddKey(g)];
   return '<div class="odd-group"><label><b>'+(g.items.length>1?'Pari personnalisé + ('+g.items.length+' marchés)':'Cote individuelle')+'</b><br>'+esc(g.label)+'<small>'+esc(g.items.map(p=>MARKET[p.market].label).join(" + "))+'</small><input type="number" inputmode="decimal" min="1.01" step="0.01" data-odds="'+esc(oddKey(g))+'" placeholder="Cote réelle (ex. 1.45)" value="'+(Number(odds)>1?esc(odds):"")+'"></label></div>'
 }).join("");
 updateReturn();
}
function updateReturn(){
 const all=groups(),stake=Math.max(0,Number($("stake").value)||0);
 let total=1,ok=all.length>0;
 for(const g of all){const odd=Number(state.odds[oddKey(g)]);if(!(odd>1&&Number.isFinite(odd))){ok=false;break}total*=odd}
 $("total-odds").textContent=ok?total.toFixed(2):"—";
 $("payout").textContent=ok?money(stake*total):"—";
 $("profit").textContent=ok?money(stake*(total-1)):"—";
}
function filteredForBuilder(){
 const v=$("builder-comp").value;
 return state.fixtures.filter(f=>upcoming(f)&&(v==="all"||f.competition===v||f.kind===v));
}
function candidates(mode,fixture){
 const cfg=MODE[mode],ss=stats(fixture);
 if(ss.home.n<cfg.minSample||ss.away.n<cfg.minSample)return [];
 return cfg.list.map(mid=>({eventId:fixture.id,competition:fixture.competition,home:fixture.home.name,away:fixture.away.name,market:mid,idx:index(fixture,mid),fixture}))
   .filter(x=>x.idx!==null&&x.idx>=cfg.minIndex).sort((a,b)=>b.idx-a.idx);
}
function build(mode,count,allowMulti){
 const all=filteredForBuilder().flatMap(f=>candidates(mode,f)).sort((a,b)=>b.idx-a.idx);
 const picks=[],seen=new Map();
 for(const p of all){
   const n=seen.get(p.eventId)||0;
   if(n>=(allowMulti?2:1))continue;
   const base={eventId:p.eventId,competition:p.competition,home:p.home,away:p.away,market:p.market,index:p.idx};
   picks.push(base);seen.set(p.eventId,n+1);
   if(picks.length>=count)break;
 }
 return picks;
}
async function prepareBuilder(){
 const relevant=new Set(filteredForBuilder().map(f=>f.competition));
 if(!relevant.size){$("builder-message").textContent="Aucun match encore à venir pour les filtres choisis.";return false}
 const missing=[...relevant].filter(x=>!state.histories[x]);
 $("builder-message").textContent=missing.length?"Lecture des historiques par compétition : "+missing.length+" chargement(s)…":"Historiques prêts.";
 // Limit simultaneous historical fetches; the backend caches each competition for one hour.
 let failures=[];
 for(let start=0;start<missing.length;start+=3){
  const piece=missing.slice(start,start+3);
  await Promise.all(piece.map(async comp=>{try{await getHistory(comp)}catch(e){failures.push(comp)}}));
  $("builder-message").textContent=(Math.min(start+3,missing.length))+"/"+missing.length+" historique(s) consulté(s).";
 }
 if(failures.length){$("builder-message").textContent="Certaines compétitions sont indisponibles ("+failures.join(", ")+"). Les propositions n'utilisent que les historiques récupérés."}
 return true;
}
async function generate(){
 const btn=$("generate");btn.disabled=true;btn.textContent="Chargement des statistiques…";
 try{
  if(!(await prepareBuilder()))return;
  const mode=$("mode").value,n=Math.max(2,Math.min(8,+$("n-picks").value)),multi=$("associations").value==="multi";
  const out=build(mode,n,multi);
  if(!out.length){$("builder-message").textContent="Aucun marché avec un historique suffisant dans les matchs à venir. En coupe ou en Europe, l'échantillon peut être trop petit : sélection manuelle possible après analyse.";return}
  state.picks=out;state.odds={};persist();renderCoupon();
  $("builder-message").textContent=out.length+" marché(s) retenu(s). Mode "+MODE[mode].label+" — indices descriptifs, aucun gain garanti. Composition, absences et cotes à vérifier.";
 }catch(e){$("builder-message").textContent="Erreur de génération : "+e.message}
 finally{btn.disabled=false;btn.textContent="✨ Générer mon coupon"}
}
async function variants(){
 const btn=$("variants");btn.disabled=true;
 try{
  if(!(await prepareBuilder()))return;
  const allow=$("associations").value==="multi";
  state.variants=[["prudent",3],["equilibre",4],["exploratoire",6]].map(([mode,n])=>({mode,picks:build(mode,n,allow)}));
  $("variant-list").innerHTML=state.variants.map((v,i)=>'<div class="variant"><h4>'+MODE[v.mode].label+' · '+v.picks.length+' sélection(s)</h4><p>'+esc(v.picks.map(p=>p.home+" – "+p.away+" : "+MARKET[p.market].label).join(" • ")||"Pas assez de données historiques dans les compétitions à venir.")+'</p><button class="sub-btn" data-variant="'+i+'" '+(v.picks.length?"":"disabled")+'>Utiliser ce coupon</button></div>').join("");
 }finally{btn.disabled=false}
}
function copy(){
 if(!state.picks.length)return alert("Ton coupon est vide.");
 const s=["FOOTBALL POINT RADAR — COUPON",state.date,"",...state.picks.map(p=>p.home+" – "+p.away+" : "+MARKET[p.market].label+" ("+p.competition+")"),"",...groups().map(g=>g.label+" : "+(Number(state.odds[oddKey(g)])>1?state.odds[oddKey(g)]:"cote à renseigner")),"","Mise : "+$("stake").value+" CHF","Indices historiques, non des probabilités garanties."].join("\n");
 if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(s).then(()=>alert("Coupon copié.")).catch(()=>prompt("Copier :",s));else prompt("Copier :",s)
}
async function loadFixtures(day){
 state.date=day;$("match-date").value=day;
 $("match-list").className="match-list empty";$("match-list").textContent="Chargement des matchs…";
 try{
  const r=await fetch("/api/fixtures?date="+encodeURIComponent(day)),d=await r.json();
  if(!r.ok)throw Error(d.error||r.status);
  if(day!==state.date)return;
  state.fixtures=d.fixtures||[];state.errors=d.errors||[];
  note("Calendrier chargé : "+state.fixtures.length+" match(s) · "+new Set(state.fixtures.map(f=>f.competition)).size+" compétition(s)"+(d.partial?" · certaines compétitions indisponibles":"")+".",!!d.partial);
  renderFixtures();renderCoupon();
 }catch(e){state.fixtures=[];renderFixtures();note("Calendrier indisponible : "+e.message,true)}
}
async function init(){
 readSaved();let day=tzDay();$("match-date").value=day;
 document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click",()=>tab(b.dataset.tab)));
 $("match-date").addEventListener("change",e=>loadFixtures(e.target.value));
 ["kind-filter","comp-filter"].forEach(id=>$(id).addEventListener("change",renderFixtures));
 $("generate").addEventListener("click",generate);
 $("variants").addEventListener("click",variants);
 $("clear").addEventListener("click",()=>{state.picks=[];state.odds={};persist();renderCoupon()});
 $("stake").addEventListener("input",()=>{persist();updateReturn()});
 $("copy").addEventListener("click",copy);
 $("odds-inputs").addEventListener("input",e=>{const k=e.target.dataset.odds;if(k){state.odds[k]=e.target.value;persist();updateReturn()}});
 document.addEventListener("click",e=>{
  const a=e.target.closest("[data-analyze]");if(a){analyze(a.dataset.analyze);return}
  const b=e.target.closest("[data-market]");if(b){addPick(b.dataset.game,b.dataset.market);return}
  const c=e.target.closest("[data-remove]");if(c){state.picks.splice(+c.dataset.remove,1);state.odds={};persist();renderCoupon();return}
  const d=e.target.closest("[data-variant]");if(d){const v=state.variants[+d.dataset.variant];if(v){state.picks=v.picks;state.odds={};persist();renderCoupon();tab("coupons")}}
 });
 try{const r=await fetch("/api/competitions");const d=await r.json();state.competitions=d.competitions||[];renderOptions()}
 catch(e){note("Impossible de charger les compétitions : "+e.message,true)}
 await loadFixtures(day);
 setInterval(()=>{if(!document.hidden)loadFixtures(state.date)},5*60*1000);
}
document.addEventListener("DOMContentLoaded",init);
