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
  function labels(){
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
