import {X} from 'lucide-react';
import {date, incidentNames, type Row} from './api';
import {useModalFocus} from './useModalFocus';

type Props = {rows:Row[];username:string;sound:boolean;busy:boolean;error:string;objectName:(id:string)=>string;onSound:(value:boolean)=>void;onClose:()=>void;onOpen:(row:Row)=>void};

export function NotificationInbox({rows,username,sound,busy,error,objectName,onSound,onClose,onOpen}:Props){
  useModalFocus(true,'.notification-panel');
  return <div className="overlay notification-overlay" onClick={onClose}>
    <section className="notification-panel" role="dialog" aria-modal="true" aria-labelledby="notification-inbox-title" onClick={event=>event.stopPropagation()} onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();onClose()}}}>
      <div className="panel-title"><h2 id="notification-inbox-title">Уведомления</h2><button type="button" onClick={onClose} aria-label="Закрыть уведомления"><X/></button></div>
      <label className="check"><input type="checkbox" checked={sound} onChange={event=>onSound(event.target.checked)}/>Звук новых уведомлений</label>
      {busy&&<p role="status">Открываем прогноз…</p>}
      {error&&<p role="alert" className="error">{error}</p>}
      {rows.length?rows.map(row=>{
        const probability=row.data?.probability;
        return <button type="button" key={row.id} className="notification-item" disabled={busy||!row.data?.prediction_id} onClick={()=>onOpen(row)}>
          <strong>{incidentNames[row.data?.incident_type]??'Сигнал'} · {objectName(row.object_id)}</strong>
          <small>{date(row.ts)} · {typeof probability==='number'&&Number.isFinite(probability)?`${Math.round(probability*100)}%`:'Нет оценки'}</small>
          <span>{row.data?.read_by?.includes(username)?'Прочитано':'Новое'}</span>
          {!row.data?.prediction_id&&<small>Прогноз не прикреплён</small>}
        </button>;
      }):<p className="empty">Уведомлений пока нет</p>}
    </section>
  </div>;
}
