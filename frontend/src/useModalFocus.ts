import {useEffect} from 'react';

/** Keep keyboard navigation in an open dialog and restore the previous control. */
export function useModalFocus(open:boolean, selector:string){
 useEffect(()=>{
  if(!open)return;
  const dialog=document.querySelector<HTMLElement>(selector);
  if(!dialog)return;
  const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
  const overflow=document.body.style.overflow;
  const controls=()=>Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')).filter(el=>el.getClientRects().length>0);
  controls()[0]?.focus();document.body.style.overflow='hidden';
  const trap=(event:KeyboardEvent)=>{if(event.key!=='Tab')return;const items=controls(),first=items[0],last=items[items.length-1];if(!first){event.preventDefault();return}if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}};
  dialog.addEventListener('keydown',trap);
  return()=>{dialog.removeEventListener('keydown',trap);document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus()};
 },[open,selector]);
}
