import {useState} from 'react';
import {ArrowUpRight, MessageSquareText} from 'lucide-react';
import {api, Row, date} from './api';
import './repair-workspace.css';

type Props = {
  rows: Row[];
  selectedId?: string|null;
  onClearSelection?: () => void;
  role: string;
  objectName: (id: string) => string;
  maintenanceNote?: string;
  onRefresh: () => Promise<void>;
  onStatus: (id: string, status: string) => void;
  onDraft: (id: string) => void;
};

const statusNames: Record<string,string> = {new:'Новая', accepted:'Принята', rejected:'Отклонена', completed:'Выполнена'};

export function RecommendationsPanel({rows, selectedId, onClearSelection, role, objectName, maintenanceNote, onRefresh, onStatus, onDraft}: Props) {
  const [query,setQuery]=useState('');
  const [status,setStatus]=useState('');
  const visible=rows.filter(row=>selectedId ? row.id===selectedId : (!status||row.data?.status===status)&&`${objectName(row.object_id)} ${row.data?.action??''}`.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')));
  const [drafts, setDrafts] = useState<Record<string,string>>({});
  const [saving, setSaving] = useState<string|null>(null);
  const [error, setError] = useState<string|null>(null);
  const canWrite = ['technician','dispatcher','admin'].includes(role);

  async function saveNote(id: string) {
    const text = drafts[id]?.trim();
    if (!text || text.length < 3) return;
    setSaving(id);
    setError(null);
    try {
      await api(`/recommendations/${id}/notes`, {text});
      await onRefresh();
      setDrafts(old => ({...old, [id]: ''}));
    } catch (cause) {setError(cause instanceof Error ? cause.message : 'Не удалось сохранить комментарий');}
    finally {setSaving(null);}
  }

  return <section className={`panel repair-panel repair-panel--${role}`} aria-label="План профилактических работ">
    <div className="panel-title"><div><span className="control-kicker">РАБОЧАЯ КАРТА / ОБСЛУЖИВАНИЕ</span><h2>{role === 'technician' ? 'Что проверить на объекте' : 'План профилактических работ'}</h2><p>{maintenanceNote}</p></div></div>
    <div className="repair-toolbar">{selectedId ? <><button type="button" onClick={onClearSelection}>← Все работы ({rows.length})</button><span>Выбранная работа</span></> : <><label>Найти работу<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Участок или действие"/></label><label>Статус работы<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Все статусы</option>{Object.entries(statusNames).map(([value,name])=><option key={value} value={value}>{name}</option>)}</select></label><span role="status">Найдено: {visible.length} из {rows.length}</span>{(query||status)&&<button type="button" onClick={()=>{setQuery('');setStatus('')}}>Сбросить фильтры</button>}</>}</div>
    {role === 'technician' && <details className="repair-guidance"><summary>Перед выполнением: регламент и допуск</summary><p>Сверьте показания и журнал события, проверьте действующий регламент и допуск. Действие ниже — рекомендация системы, а не дистанционная команда оборудованию.</p></details>}
    {visible.length ? visible.map(r => <article className="recommendation repair-card" key={r.id} aria-label={`Работа: ${objectName(r.object_id)}`}>
      <strong className="priority">{r.data?.priority ?? '—'}<small>приоритет</small></strong>
      <div className="repair-card-main"><span className="control-kicker">{objectName(r.object_id)} / {statusNames[r.data?.status] ?? 'Статус не указан'}</span><h3>{r.data?.action ?? 'Проверить объект'}</h3><p>{r.data?.window_from && r.data?.window_to ? `${date(r.data.window_from)} — ${date(r.data.window_to)}` : 'Время работ не назначено'}</p>
        <div className="repair-evidence"><span>Основание: {r.data?.schedule_comparison ?? 'Нет сравнения с планом'}</span><span>Риск: {typeof r.data?.rationale?.probability === 'number' ? `${Math.round(r.data.rationale.probability * 100)}%` : 'нет оценки'}</span></div>
        <div className="repair-notes"><h4><MessageSquareText size={16}/> Комментарии бригады и диспетчера</h4>{(r.data?.work_notes ?? []).length ? r.data.work_notes.map((note: Row, index: number) => <p key={`${note.ts}-${index}`}><b>{note.author}</b> <time>{note.ts ? date(note.ts) : ''}</time><span>{note.text}</span></p>) : <p className="repair-note-empty">Пока нет комментариев к этой работе.</p>}
          {canWrite && <form onSubmit={event => {event.preventDefault(); void saveNote(r.id);}}><label htmlFor={`note-${r.id}`}>Что проверили и что нужно знать следующей смене</label><textarea id={`note-${r.id}`} value={drafts[r.id] ?? ''} minLength={3} maxLength={1000} onChange={event => setDrafts(old => ({...old, [r.id]: event.target.value}))} placeholder="Например: сверили показания, требуется очная проверка…"/><button type="submit" disabled={saving === r.id || (drafts[r.id]?.trim().length ?? 0) < 3}>{saving === r.id ? 'Сохраняю…' : 'Оставить комментарий'}</button></form>}
        </div>
      </div>
      <div className="actions">{canWrite && <><button disabled={r.data?.status==='accepted'||r.data?.status==='completed'} onClick={() => onStatus(r.id, 'accepted')}>Принять</button><button disabled={r.data?.status==='completed'} onClick={() => onStatus(r.id, 'completed')}>Выполнено</button></>}{['admin','dispatcher'].includes(role)&&<button onClick={() => onDraft(r.id)}>Черновик заявки <ArrowUpRight size={14}/></button>}</div>
    </article>) : <p className="role-empty">{selectedId?'Выбранная работа больше недоступна. Вернитесь ко всем работам.':rows.length?'По этим условиям работ нет. Измените запрос или сбросьте фильтры.':'Рекомендаций в текущем срезе нет.'}</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
