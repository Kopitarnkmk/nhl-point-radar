"use strict";
const $=x=>document.getElementById(x),state={date:"",matches:[],selected:null,picks:[],odds:{}};
const esc=x=>String(x??"").replace(/[&<>"']/g,k=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[k]));
const daytime=x=>new Intl.DateTimeFormat("fr-CH",{timeZone:"Europe/Zurich",weekday:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(x));
const today=()=>new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Zurich",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
function tab(s){document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.tab===s));document.querySelectorAll(".panel").forEach(x=>x.classList.toggle("active",x.id==="panel-"+s))}
function store(){localStorage.setItem("tennis-radar",JSON.stringify({picks:state.picks,odds:state.odds,stake:$("stake").value}))}
function restore(){try{let a=JSON.parse(localStorage.getItem("tennis-radar")||"{}");state.picks=a.picks||[];state.odds=a.odds||{};if(a.stake)$("stake").value=a.stake}catch{}}
function upcoming(m){return m.state==="pre"&&Date.parse(m.date)>Date.now()}
async function read(date){
 state.date=date;$("date").value=date;$("status").textContent="Lecture des rencontres ATP et WTA…";
 try{let r=await fetch("/api/matches?date="+encodeURIComponent(date)),d=await r.json();if(!r.ok)throw Error(d.error||r.status);
 state.matches=d.matches||[];$("count").textContent=state.matches.length;
 $("status").textContent=state.matches.length+" rencontres · ATP/WTA · "+date+(d.errors?.length?" · données partielles":"");renderMatches();
 }catch(e){$("status").textContent="Données tennis indisponibles : "+e.message}
}
function renderMatches(){
 let tour=$("tour").value,q=$("search").value.toLowerCase().trim();
 const games=state.matches.filter(m=>(tour==="all"||tour===m.tour)&&(!q||(m.a.name+" "+m.b.name+" "+m.tournament).toLowerCase().includes(q)));
 $("matches").innerHTML=games.map(m=>'<article class="game"><div class="muted">'+esc(m.tour.toUpperCase())+' · '+esc(m.tournament)+' · '+esc(m.round||"Tour")+'</div><div class="muted">'+esc(daytime(m.date))+' · '+esc(upcoming(m)?"À venir":m.complete?"Terminé":"En cours / programmé")+'</div><h4>'+esc(m.a.name)+'<span> VS </span>'+esc(m.b.name)+'</h4><button class="primary" data-match="'+esc(m.id)+'">Comparer les joueurs</button></article>').join("")||'<p class="muted">Aucun match trouvé pour ce filtre.</p>';
}
function analyze(id){
 const m=state.matches.find(x=>x.id===id);if(!m)return;
 state.selected=m;tab("analyse");$("analysis-title").textContent=m.a.name+" – "+m.b.name;
 const current=m.model;
 const player=p=>'<div class="tennis-player"><h4>'+esc(p.name)+'</h4><div><small>Classement</small><strong>'+(p.rank?"N° "+p.rank:"—")+'</strong></div><div><small>Matchs récents analysés</small><strong>'+p.last10+'</strong></div><div><small>Victoires récentes</small><strong>'+p.last10Wins+'/'+p.last10+'</strong></div><div><small>% récent observé</small><strong>'+(p.last10WinPct==null?"—":p.last10WinPct+" %")+'</strong></div></div>';
 $("analysis").innerHTML='<div class="muted">'+esc(m.tournament)+' · '+esc(m.round||"")+" · "+esc(m.surface||"Surface non renseignée")+'</div>'+
 (current?'<div class="projection"><div><small>VICTOIRE '+esc(m.a.name)+'</small><strong>'+current.aWinPct+' %</strong></div><div><small>VICTOIRE '+esc(m.b.name)+'</small><strong>'+current.bWinPct+' %</strong></div></div><p class="muted">'+esc(current.label)+' '+esc(current.limitations)+'</p>':'<p class="warning">Pas de prévision disponible : au moins un joueur n’a pas de classement exploitable.</p>')+
 '<div class="tennis-players">'+player(m.a)+player(m.b)+'</div><p class="muted">Ces indicateurs ne tiennent pas lieu de modèle de surface calibré. Vérifie les blessures, la fatigue, le format et les cotes.</p>'+
 (upcoming(m)?'<div class="actions"><button class="primary" data-pick="'+esc(m.a.id)+'">Ajouter '+esc(m.a.name)+'</button><button class="sub" data-pick="'+esc(m.b.id)+'">Ajouter '+esc(m.b.name)+'</button></div>':'<p class="muted">Match commencé : ajout non proposé.</p>');
}
function add(id){
 const m=state.selected;if(!m||!upcoming(m))return;
 if(state.picks.length>=8)return alert("Maximum 8 sélections");
 let p=m.a.id===id?m.a:m.b;
 if(state.picks.some(x=>x.match===m.id))return alert("Un seul vainqueur par rencontre.");
 state.picks.push({match:m.id,tour:m.tour,tournament:m.tournament,player:p.name,opponent:(p.id===m.a.id?m.b.name:m.a.name)});
 state.odds={};store();renderCoupon();tab("coupon");
}

function generateCouponTennis(){
 const mode=$("auto-mode").value,n=Number($("auto-count").value),tour=$("auto-tour").value,msg=$("auto-feedback");
 const candidates=[];
 for(const m of state.matches){
  if(!upcoming(m)||(tour!=="all"&&m.tour!==tour)||!m.model)continue;
  const p=m.model.aWinPct>=m.model.bWinPct?m.a:m.b;
  const q=p.id===m.a.id?m.b:m.a;
  const rate=Math.max(m.model.aWinPct,m.model.bWinPct);
  if(p.last10<3||q.last10<3)continue;
  const valid=mode==="prudent"?rate>=70&&p.last10Wins/p.last10>=.55:
       mode==="equilibre"?rate>=58&&rate<70:
       rate>=50&&rate<58;
  if(!valid)continue;
  candidates.push({match:m.id,tour:m.tour,tournament:m.tournament,player:p.name,opponent:q.name,
                   index:rate,form:p.last10Wins+"/"+p.last10,level:mode,start:m.date});
 }
 candidates.sort((a,b)=>mode==="exploratoire"?a.index-b.index:b.index-a.index);
 const chosen=candidates.slice(0,n);
 if(!chosen.length){
  msg.textContent="Aucun match encore à venir ne correspond aux critères du mode "+mode+". Réessaie un autre mode, une autre date ou un autre tour.";
  return;
 }
 state.picks=chosen;state.odds={};store();renderCoupon();
 msg.textContent=chosen.length+"/"+n+" suggestions. Indice heuristique fondé sur classement et forme récente, NON calibré en probabilité de victoire. Vérifie surface, fatigue, blessures et cotes.";
}
function renderCoupon(){
 $("picks-count").textContent=state.picks.length;
 $("picks").innerHTML=state.picks.map((p,i)=>'<div class="pick"><div><b>'+esc(p.player)+' gagne</b><small>'+esc(p.tournament)+' vs '+esc(p.opponent)+(p.form?' · Forme : '+esc(p.form)+' · Indice : '+esc(p.index)+'/100':'')+'</small></div><button class="sub" data-remove="'+i+'">✕</button></div>').join("")||'<p class="muted">Aucun joueur choisi.</p>';
 $("odds").innerHTML=state.picks.map((p,i)=>'<div class="odd"><label>Cote de '+esc(p.player)+'<input type="number" min="1.01" step=".01" data-odd="'+p.match+'" placeholder="Cote bookmaker" value="'+esc(state.odds[p.match]||"")+'"></label></div>').join("");
 calc();
}
function calc(){let ok=state.picks.length>0,product=1;state.picks.forEach(p=>{let v=Number(state.odds[p.match]);if(!(v>1))ok=false;else product*=v});let stake=Number($("stake").value)||0;$("total").textContent=ok?product.toFixed(2):"—";$("payout").textContent=ok?(stake*product).toFixed(2)+" CHF":"—";$("profit").textContent=ok?(stake*(product-1)).toFixed(2)+" CHF":"—"}
function copy(){let txt=["TENNIS RADAR",...state.picks.map(p=>p.player+" vainqueur vs "+p.opponent+" : "+(state.odds[p.match]||"cote à saisir"))].join("\n");if(navigator.clipboard)navigator.clipboard.writeText(txt).then(()=>alert("Copié"));else prompt("Copie :",txt)}
document.addEventListener("DOMContentLoaded",()=>{restore();renderCoupon();read(today());
 document.querySelectorAll("nav button").forEach(b=>b.addEventListener("click",()=>tab(b.dataset.tab)));
 $("tour").addEventListener("change",renderMatches);$("search").addEventListener("input",renderMatches);$("date").addEventListener("change",e=>read(e.target.value));
 $("auto-generate").addEventListener("click",generateCouponTennis);
 $("clear").addEventListener("click",()=>{state.picks=[];state.odds={};store();renderCoupon()});$("copy").addEventListener("click",copy);
 $("stake").addEventListener("input",()=>{store();calc()});$("odds").addEventListener("input",e=>{let id=e.target.dataset.odd;if(id){state.odds[id]=e.target.value;store();calc()}});
 document.addEventListener("click",e=>{let b=e.target.closest("[data-match]");if(b){analyze(b.dataset.match);return}b=e.target.closest("[data-pick]");if(b){add(b.dataset.pick);return}b=e.target.closest("[data-remove]");if(b){state.picks.splice(+b.dataset.remove,1);state.odds={};store();renderCoupon()}});
 setInterval(()=>{if(!document.hidden)read(state.date)},10*60*1000);
});
