import { createContext, useContext, useEffect, useLayoutEffect, useRef } from 'react';

export const EditScope=createContext('workspace');
const edits=new Map<symbol,{scope:string;dirty:boolean}>();

export function confirmDiscard(scope:string) {
  const pending=[...edits].filter(([,entry])=>entry.scope===scope&&entry.dirty);
  if(!pending.length)return true;
  if(!window.confirm(`Discard unsaved changes in ${scope}?`))return false;
  pending.forEach(([key])=>edits.delete(key));
  return true;
}

export function useUnsavedChanges(dirty:boolean, explicitScope?:string) {
  const inherited=useContext(EditScope),scope=explicitScope||inherited,key=useRef(Symbol('edit'));
  useLayoutEffect(()=>{const id=key.current;edits.set(id,{scope,dirty});return()=>{edits.delete(id);};},[dirty,scope]);
  useEffect(()=>{
    if(!dirty)return;
    const prevent=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',prevent);
    return()=>window.removeEventListener('beforeunload',prevent);
  },[dirty]);
}
