import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { X, Pin, PinOff, Minus, Maximize2 } from 'lucide-react';
import { EditScope, confirmDiscard } from './Unsaved';
import { PanelErrorBoundary } from './PanelErrorBoundary';

export const PanelLayoutContext=createContext<{pinned:string[];pin:(title:string,value:boolean)=>void}>({pinned:[],pin:()=>{}});
interface Bounds {x:number;y:number;width:number;height:number}
function fitted(b:Bounds):Bounds {
  const width=Math.min(Math.max(300,b.width),innerWidth-24),height=Math.min(Math.max(220,b.height),innerHeight-24);
  return {width,height,x:Math.max(12,Math.min(b.x,innerWidth-width-12)),y:Math.max(12,Math.min(b.y,innerHeight-height-12))};
}
export function Modal({title,subtitle,onClose,children,wide=false}:{title:string;subtitle?:string;onClose:()=>void;children:ReactNode;wide?:boolean}) {
  const context=useContext(PanelLayoutContext),pinned=context.pinned.includes(title),pinnable=!['Command center','Create a flow','Welcome to Stonic'].includes(title);
  const ref=useRef<HTMLDivElement>(null),close=useRef(onClose),drag=useRef<{x:number;y:number;bounds:Bounds}|null>(null);
  const guardedClose=()=>{if(confirmDiscard(title))onClose();};
  close.current=guardedClose;
  const [minimized,setMinimized]=useState(false),[layer,setLayer]=useState(30);
  const [bounds,setBounds]=useState<Bounds>(()=>{
    try {const saved=JSON.parse(localStorage.getItem(`stonic.panel.${title}`)||'null');if(saved&&['x','y','width','height'].every(k=>Number.isFinite(saved[k])))return fitted(saved);}catch{/* Reset invalid saved geometry. */}
    return fitted({x:80,y:90,width:wide?800:540,height:600});
  });
  useEffect(()=>{function resize(){setBounds(b=>fitted(b));}window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
  useEffect(()=>{
    if(!pinned||minimized||!ref.current)return;
    let timer:ReturnType<typeof setTimeout>;
    const observer=new ResizeObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>{const r=ref.current?.getBoundingClientRect();if(r)localStorage.setItem(`stonic.panel.${title}`,JSON.stringify({x:r.x,y:r.y,width:r.width,height:r.height}));},150);});
    observer.observe(ref.current);return()=>{observer.disconnect();clearTimeout(timer);};
  },[pinned,minimized,title]);
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement;ref.current?.focus();
    function keydown(event:KeyboardEvent){
      if(pinned&&!ref.current?.contains(document.activeElement))return;
      if(event.key==='Escape'){event.stopPropagation();close.current();}
      if(!pinned&&event.key==='Tab'){
        const nodes=Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea, select, [tabindex="0"]')||[]).filter(e=>e.offsetParent!==null);
        if(!nodes.length){event.preventDefault();return;}
        const first=nodes[0],last=nodes[nodes.length-1];
        if(event.shiftKey&&(document.activeElement===first||document.activeElement===ref.current)){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===ref.current)){event.preventDefault();first.focus();}
      }
    }
    document.addEventListener('keydown',keydown);return()=>{document.removeEventListener('keydown',keydown);if(!pinned)previous?.focus();};
  },[pinned]);
  function move(next:Bounds){const value=fitted(next);setBounds(value);localStorage.setItem(`stonic.panel.${title}`,JSON.stringify(value));}
  return <div className={`modal-backdrop ${pinned?'floating-backdrop':''}`} style={{zIndex:pinned?layer:1000000}} onMouseDown={e=>{if(!pinned&&e.target===e.currentTarget)guardedClose();}}>
    <div ref={ref} tabIndex={-1} role="dialog" aria-modal={!pinned} aria-label={title} className={`modal ${wide?'modal-wide':''} ${pinned?'floating-panel':''} ${minimized?'panel-minimized':''}`} style={pinned?{left:bounds.x,top:bounds.y,width:bounds.width,height:minimized?84:bounds.height}:undefined} onPointerDownCapture={()=>{if(pinned)setLayer(30+Date.now()%999000);}}>
      <header className="modal-header" tabIndex={pinned?0:undefined} aria-label={pinned?`Move ${title} panel with Alt and arrow keys`:undefined}
        onKeyDown={e=>{if(pinned&&e.altKey&&e.key.startsWith('Arrow')){e.preventDefault();move({...bounds,x:bounds.x+(e.key==='ArrowRight'?10:e.key==='ArrowLeft'?-10:0),y:bounds.y+(e.key==='ArrowDown'?10:e.key==='ArrowUp'?-10:0)});}}}
        onPointerDown={e=>{if(!pinned||(e.target as HTMLElement).closest('button'))return;const r=ref.current!.getBoundingClientRect();drag.current={x:e.clientX,y:e.clientY,bounds:{x:r.x,y:r.y,width:r.width,height:minimized?bounds.height:r.height}};e.currentTarget.setPointerCapture(e.pointerId);}}
        onPointerMove={e=>{if(drag.current){const start=drag.current;move({...start.bounds,x:start.bounds.x+e.clientX-start.x,y:start.bounds.y+e.clientY-start.y});}}} onPointerUp={()=>{drag.current=null;}} onLostPointerCapture={()=>{drag.current=null;}}>
        <div><span className="eyebrow">STONIC WORKSPACE</span><h2>{title}</h2>{subtitle&&!minimized?<p>{subtitle}</p>:null}</div><div className="panel-controls">
          {pinned&&<button className="icon-button" aria-label={minimized?'Restore panel':'Minimize panel'} onClick={()=>setMinimized(!minimized)}>{minimized?<Maximize2 size={16}/>:<Minus size={16}/>}</button>}
          {pinnable&&<button className="icon-button" aria-label={pinned?'Unpin panel':'Pin panel'} onClick={()=>{setMinimized(false);context.pin(title,!pinned);}}>{pinned?<PinOff size={16}/>:<Pin size={16}/>}</button>}
          <button className="icon-button" aria-label="Close panel" onClick={guardedClose}><X size={18}/></button></div>
      </header><EditScope.Provider value={title}><PanelErrorBoundary title={title}>{children}</PanelErrorBoundary></EditScope.Provider>
    </div>
  </div>;
}
