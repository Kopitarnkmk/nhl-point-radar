/* ValueRadar | Accessible client for live odds — no demo picks, no paid APIs. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { data:null, sport:'all', minEdge:7, view:'signals', loading:false, error:'', lastSuccess:null };
  const timezone = 'Europe/Zurich';
  const icons = {soccer:'⚽',nba:'🏀',nhl:'🏒'};
  const names = {soccer:'Football',nba:'NBA',nhl:'NHL'};
  const escape = (text) => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function localTime(iso, options={}) {
    const date = new Date(iso || '');
    if (Number.isNaN(date.getTime())) return 'Indisponible';
    return new Intl.DateTimeFormat('fr-CH',{timeZone:timezone,day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',...options}).format(date);
  }
  function shortTime(iso) {
    const date=new Date(iso||'');
    return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('fr-CH',{timeZone:timezone,hour:'2-digit',minute:'2-digit'}).format(date) : '—';
  }
  function age(iso) {
    const t=Date.parse(iso || '');
    if (!Number.isFinite(t)) return 'Heure inconnue';
    const diff=Math.floor((Date.now()-t)/60000);
    if(diff<0) return 'Horodatage futur';
    if(diff<2) return 'À l’instant';
    if(diff<60) return `Il y a ${diff} min`;
    return `Il y a ${Math.floor(diff/60)} h`;
  }
  function num(value,digits=2) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString('fr-CH',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—'; }
  function validExternal(url) {try {const u=new URL(url);return u.protocol==='https:' ? u.href : '';}catch{return '';}}
  function selectedSignals() {
    if (!state.data) return [];
    return [...(state.data.signals || []),...(state.data.watch||[])].filter(x=>{
      return Number(x.edge)>=state.minEdge && (state.sport==='all'||x.sport===state.sport);
    }).sort((a,b)=>b.edge-a.edge);
  }
  function selectedWatch() {
    if (!state.data) return [];
    return (state.data.watch||[]).filter(x=>state.sport==='all'||x.sport===state.sport);
  }
  function selectedGames() {
    if (!state.data) return [];
    return (state.data.games||[]).filter(x=>state.sport==='all'||x.sport===state.sport);
  }
  function empty(title, desc, extra='') {
    return `<div class="empty no-results ${extra}"><div class="empty-icon">⌁</div><h3>${escape(title)}</h3><p>${escape(desc)}</p></div>`;
  }
  function item(signal) {
    const isPotential=Number(signal.edge)>=7;
    const grade=isPotential?'À VÉRIFIER':'SURVEILLANCE';
    const bookTime=signal.book_price_at?age(signal.book_price_at):'Horodatage non fourni';
    const sport=escape(names[signal.sport] || signal.sport);
    const line=signal.line===null||signal.line===undefined ? '' : ` · Ligne ${escape(signal.line)}`;
    const link=validExternal(signal.link);
    return `<article class="signal ${isPotential?'':'watch'}">
      <div><div class="signal-head"><span class="signal-tag">${grade}</span><span class="sport-pill">${icons[signal.sport]||'◉'} ${sport} · ${escape(localTime(signal.starts_at))}</span></div>
      <div class="signal-title">${escape(signal.away)} <span style="color:#829a9d;font-weight:450">vs</span> ${escape(signal.home)}</div>
      <div class="signal-meta">${escape(signal.market_label||signal.market)} · <strong>${escape(signal.selection)}</strong>${line}</div></div>
      <div class="edge-box"><small>EDGE ESTIMÉ</small><div class="edge-number">+${num(signal.edge,1)}%</div></div>
      <div class="signal-quotes"><div class="quote-box"><small>BOOKMAKER</small><strong>${escape(signal.bookmaker)}</strong></div>
      <span class="quote-sep"></span><div class="quote-box"><small>COTE OBSERVÉE</small><strong class="good">${num(signal.offered)}</strong></div>
      <span class="quote-sep"></span><div class="quote-box"><small>COTE THÉORIQUE</small><strong>${num(signal.fair)}</strong></div>
      <div class="quote-time">${escape(bookTime)}</div></div>
      <div class="signal-foot"><span>⚠ Prix à confirmer directement chez l'opérateur. Suisse non vérifiée.</span>${link?`<a href="${escape(link)}" target="_blank" rel="noopener noreferrer">Voir la cote ↗</a>`:''}</div>
    </article>`;
  }
  function gameItem(game){
    const date=new Date(game.starts_at);
    const dateText=Number.isFinite(date.getTime())?localTime(game.starts_at):'—';
    const markets=(game.market_types||[]).slice(0,2).join(' · ')||'Marchés indisponibles';
    return `<article class="game"><div><div class="game-kicker">${icons[game.sport]||'◉'} ${escape(game.sport_label||names[game.sport]||game.sport)} ${game.league?`<small>· ${escape(game.league)}</small>`:''}</div>
      <h3>${escape(game.away)} <span style="color:#68808e;font-weight:450">vs</span> ${escape(game.home)}</h3>
      <div class="game-note">${escape(game.books_count)} books observés · ${escape(markets)}</div></div>
      <div class="game-aside"><small>${escape(dateText)}</small><strong>${escape(shortTime(game.starts_at))}</strong>${game.has_pinnacle?'<span class="event-small">Réf. Pinnacle ✓</span>':'<span class="event-small">Réf. indisponible</span>'}</div></article>`;
  }
  function render() {
    const data=state.data, feed=$('feed');
    if (!data) {
      if(state.error) feed.innerHTML=empty('Source temporairement indisponible','Aucune cote inventée. Réessaie dans quelques instants.','error-box');
      return;
    }
    const sig=selectedSignals(),watch=selectedWatch(),games=selectedGames();
    $('stat-signals').textContent=(data.stats?.signals??0).toLocaleString('fr-CH');
    $('stat-watch').textContent=(data.stats?.watch??0).toLocaleString('fr-CH');
    $('stat-matches').textContent=(data.stats?.games??0).toLocaleString('fr-CH');
    $('stat-books').textContent=(data.stats?.bookmakers_observed??0).toLocaleString('fr-CH');
    $('sidebar-count').textContent=data.stats?.signals ?? '0';
    $('signal-tab-n').textContent=data.stats?.signals ?? '0';
    $('watch-tab-n').textContent=data.stats?.watch ?? '0';
    $('games-tab-n').textContent=data.stats?.games ?? '0';
    const partial=(data.status==='partial') || !!data.stale || !!state.error;
    $('live-state').className='system-indicator'+(partial?' error':'');
    $('live-state').innerHTML=`<span class="pulse-dot"></span>${partial?'Source partielle':'Source connectée'}`;
    $('strip-label').textContent=partial?'RÉCEPTION PARTIELLE':'RADAR CONNECTÉ';
    $('strip-detail').textContent=`${data.stats?.games??0} rencontres · ${data.stats?.signals??0} opportunités filtrées · source publique limitée`;
    $('last-update').textContent=localTime(data.scanned_at);
    let current=[];
    if(state.view==='games') current=games;
    else if(state.view==='watch') current=watch;
    else current=sig;
    $('results-count').textContent=current.length;
    if (state.view==='games') {
      feed.innerHTML=current.length?current.slice(0,60).map(gameItem).join(''):empty('Aucune rencontre disponible','Le tableau public ne présente pas de rencontre à venir pour ce filtre. La couverture gratuite est limitée.');
    } else if(state.view==='watch') {
      feed.innerHTML=current.length?current.slice(0,30).map(item).join(''):empty('Aucun match en surveillance','Aucun écart de 2 à 7 % observé sur les marchés vérifiés. Consulte les rencontres pour voir la couverture de la source.');
    }else{
      feed.innerHTML=current.length?current.slice(0,30).map(item).join(''):empty('Aucune opportunité admissible','Aucun écart ne franchit actuellement tes filtres, avec des cotes suffisamment récentes. C’est normal : mieux vaut zéro signal qu’une fausse alerte.');
    }
    document.querySelectorAll('.tab').forEach(b=>{let active=b.dataset.view===state.view;b.classList.toggle('active',active);b.setAttribute('aria-selected',active?'true':'false')});
    $('nav-live').classList.toggle('active',state.view==='signals');
    $('nav-games').classList.toggle('active',state.view==='games');
  }
  async function reload(manual=false) {
    if(state.loading)return;
    state.loading=true;
    const btn=$('refresh');btn.disabled=true;
    btn.innerHTML='<span class="refresh-icon">↻</span> Analyse en cours';
    if(!state.data) {$('live-state').className='system-indicator loading';$('strip-label').textContent='CONNEXION AU RADAR';}
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),45000);
    try{
      const response=await fetch('/api/valueradar',{cache:'no-store',signal:controller.signal});
      if(!response.ok) throw new Error('Erreur HTTP '+response.status);
      const data=await response.json();
      if(!data.ok || !Array.isArray(data.games)|| !Array.isArray(data.signals))throw new Error('Réponse du radar indisponible');
      state.data=data;state.error='';state.lastSuccess=Date.now();
      render();
    }catch(err){
      state.error=String(err?.message||err);
      if(!state.data){$('live-state').className='system-indicator error';$('live-state').innerHTML='<span class="pulse-dot"></span> Hors connexion';$('strip-label').textContent='SOURCE INDISPONIBLE';$('strip-detail').textContent='Le radar ne peut pas récupérer les cotes.';render();}
      else{$('live-state').className='system-indicator error';$('live-state').innerHTML='<span class="pulse-dot"></span> Données conservées';$('strip-label').textContent='DERNIÈRES DONNÉES CONNUES';$('strip-detail').textContent='Actualisation impossible. Les cotes peuvent être périmées.';}
    }finally{clearTimeout(timeout);state.loading=false;btn.disabled=false;btn.innerHTML='<span class="refresh-icon">↻</span> Actualiser les cotes';}
  }
  $('refresh').addEventListener('click',()=>reload(true));
  $('sport-filter').addEventListener('change',e=>{state.sport=e.target.value;render()});
  $('edge-filter').addEventListener('change',e=>{state.minEdge=Number(e.target.value);state.view='signals';render()});
  document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{state.view=b.dataset.view;render()}));
  $('nav-live').addEventListener('click',()=>{state.view='signals';render();$('signals-section').scrollIntoView({behavior:'smooth'})});
  $('nav-games').addEventListener('click',()=>{state.view='games';render();$('signals-section').scrollIntoView({behavior:'smooth'})});
  reload();
  setInterval(()=>{if(!document.hidden)reload()},180000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden && (!state.lastSuccess||Date.now()-state.lastSuccess>180000))reload()});
})();