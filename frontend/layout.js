/* Layout preferences contain no coordinates. Full-screen is an in-page mode, also on Safari. */
(() => {
  'use strict';
  const A=window.SeruenApp, E=window.SeruenExt;
  const {$,state,map,T}=A, layout=$('.layout'), divider=$('#panelDivider'), panel=$('.panel'), wrap=$('.map-wrap');
  const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}};
  const save=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));}catch{}};
  let right=read('seruen_panel_right',false)===true, width=Number(read('seruen_panel_width',440))||440, drag=null, full=false, priorFocus=null;
  state.contextVersion=0;
  function resize(next=width,persist=false) {
    const max=Math.min(680,Math.max(320,window.innerWidth-328));
    width=Math.round(Math.max(320,Math.min(max,next)));
    layout.style.setProperty('--panel-width',width+'px');
    divider.setAttribute('aria-valuemin','320'); divider.setAttribute('aria-valuemax',String(max)); divider.setAttribute('aria-valuenow',String(width));
    if(persist) save('seruen_panel_width',width);
    map.invalidateSize();
  }
  // The legend names only the kinds of marks that are on the map right now (two kinds or more).
  const LEGEND=[['me','.me','lgMe'],['rec','.pin:not(.dot):not(.finish-pin)','lgRec'],['other','.pin.dot','lgOther'],['ab','.participant-pin','lgAB'],['meet','.experience-pin:not(.participant-pin)','lgMeet'],
    ['story','.story-pin','lgStory'],['rest','.cpin:not(.story-pin):not(.experience-pin)','lgRest'],['active','.active-stop-pin','lgActive'],['mine','.ppin','lgMine'],
    ['finish','.finish-pin','lgFinish'],['route','path.active-walk-path','lgRoute'],['lights','.night-light','lgLights']];
  let legendTimer=null;
  function drawLegend(){
    const box=$('#mapLegend'),root=$('#map');if(!box||!root)return;
    const on=LEGEND.filter(([,sel])=>root.querySelector(sel));
    box.hidden=on.length<2;
    box.innerHTML=on.map(([k,,key])=>`<span><i class="lg-${k}" aria-hidden="true"></i>${A.esc(T()[key]||k)}</span>`).join('');
  }
  const watchMarks=()=>{clearTimeout(legendTimer);legendTimer=setTimeout(drawLegend,150);};
  for(const pane of ['.leaflet-marker-pane','.leaflet-overlay-pane','.leaflet-neon-pane','.leaflet-lights-pane']){const el=$('#map '+pane);if(el&&window.MutationObserver)new MutationObserver(watchMarks).observe(el,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});}
  function labels(){
    drawLegend();
    // the map buttons are compact icons on wide screens: their names live in the tooltip
    setTimeout(()=>['#mapFullscreen','#panelSide'].forEach(s=>{const b=$(s);if(b)b.title=b.textContent.trim();}),0);
    $('#mapFullscreen').textContent=full?T().mapExit:T().mapFull;
    $('#mapFullscreen').setAttribute('aria-pressed',String(full));
    $('#panelSide').textContent=right?T().panelLeft:T().panelRight;
    divider.setAttribute('aria-label',T().panelResize); divider.title=T().panelResize;
  }
  function endDrag(){drag=null;document.body.classList.remove('resizing-panel');save('seruen_panel_width',width);}
  divider.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag=e.pointerId;divider.setPointerCapture?.(e.pointerId);document.body.classList.add('resizing-panel');e.preventDefault();});
  divider.addEventListener('pointermove',e=>{if(drag!==e.pointerId)return;const box=layout.getBoundingClientRect();resize(right?box.right-e.clientX:e.clientX-box.left);});
  ['pointerup','pointercancel','lostpointercapture'].forEach(name=>divider.addEventListener(name,endDrag));
  divider.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();resize(e.key==='Home'?320:e.key==='End'?680:width+(e.key==='ArrowRight'?1:-1)*(right?-24:24),true);});
  $('#panelSide').onclick=()=>{right=!right;layout.classList.toggle('panel-right',right);save('seruen_panel_right',right);resize();labels();};
  function fullscreen(value){
    if(full===value)return;
    if(value)priorFocus=document.activeElement;
    full=value;document.body.classList.toggle('map-expanded',full);
    // Keep keyboard navigation inside the visible map; restore the panel on Exit/Escape.
    for(const el of [panel,$('.top'),divider]){el.inert=full;if(full)el.setAttribute('inert','');else el.removeAttribute('inert');}
    if(full){wrap.setAttribute('role','dialog');wrap.setAttribute('aria-modal','true');}else{wrap.removeAttribute('role');wrap.removeAttribute('aria-modal');}
    labels();map.invalidateSize();
    if(full)$('#mapFullscreen').focus();else (priorFocus?.isConnected?priorFocus:$('#mapFullscreen')).focus();
  }
  $('#mapFullscreen').onclick=()=>fullscreen(!full);
  // Phones lead with the planner; the map opens full screen when a task needs it and closes after a pick.
  const phone=()=>window.matchMedia?.('(max-width: 860px)').matches;
  let pickOpen=false;
  // The map was laid out while hidden: keep the place it was asked to show, or frame you and the answer.
  const openMap=(pick=false,frame=false)=>{
    if(!phone())return;
    const c=map.getCenter(),z=map.getZoom();pickOpen=pick;fullscreen(true);
    const recs=state.last?.recommendations||[];
    if(frame&&recs.length&&window.L)A.fitTo(L.latLngBounds([[state.loc.lat,state.loc.lon],...recs.map(r=>[r.coords.lat,r.coords.lon])]),{maxZoom:16});
    else if(frame)map.setView([state.loc.lat,state.loc.lon],Math.max(z,15),{animate:false});
    else map.setView(c,z,{animate:false});
  };
  $('#mapTopBtn')?.addEventListener('click',()=>openMap(false,true));
  // ⋯ on phones: theme, language and «О данных» open as a second header row
  const more=$('#moreBtn'),top=$('.top');
  const setMore=(on)=>{top.classList.toggle('more-open',on);more?.setAttribute('aria-expanded',String(on));};
  more?.addEventListener('click',e=>{e.stopPropagation();setMore(!top.classList.contains('more-open'));});
  document.addEventListener('click',e=>{if(!e.target.closest('.top'))setMore(false);});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')setMore(false);});
  document.addEventListener('click',e=>{
    const t=e.target.closest?.('#geoMap,#locPick,#meetPick,#pickFinish,[data-act="map"],[data-nearby],[data-mine-map],[data-meet-map],.it-row');
    if(!t||!phone())return;
    const pick=t.matches('#geoMap,#locPick,#meetPick,#pickFinish');
    setTimeout(()=>openMap(pick,pick),0);
  });
  map.on('click',()=>{if(phone()&&full&&pickOpen){pickOpen=false;setTimeout(()=>fullscreen(false),700);}});
  window.SeruenLayout={openMap,closeMap:()=>fullscreen(false)};
  document.addEventListener('keydown',e=>{
    if(full&&e.key==='Escape'){e.preventDefault();fullscreen(false);}
    if(full&&e.key==='Tab'){
      const controls=[...wrap.querySelectorAll('button,select,a[href],[tabindex="0"]')].filter(el=>!el.hidden&&!el.disabled&&el.getClientRects().length);
      const first=controls[0],last=controls.at(-1);
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
    }
  });
  window.addEventListener('resize',()=>resize());
  const changed=()=>{
    state.contextVersion++;
    if($('#goBtn').disabled){state.requestVersion++;$('#goBtn').disabled=false;$('#status').textContent='';}
    $('#contextChanged').hidden=false;
  };
  $('#ctxBox').addEventListener('input',changed);$('#ctxBox').addEventListener('change',changed);
  const oldSearch=E.onSearch,oldLang=E.onLang;
  E.onSearch=(...args)=>{$('#contextChanged').hidden=true;return oldSearch?.(...args);};
  E.onLang=(...args)=>{oldLang?.(...args);labels();};
  layout.classList.toggle('panel-right',right);resize();labels();
})();
