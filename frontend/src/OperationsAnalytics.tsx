import {useMemo, useRef, useState} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {date, incidentNames, Row} from './api';
import './operations-analytics.css';

type Props = {objects: Row[]; predictions: Row[]; recommendations: Row[]; onPrediction: (row: Row) => void; onWork: (id: string) => void};
const statuses: Record<string, string> = {new: 'Новая', accepted: 'Принята', completed: 'Выполнена', rejected: 'Отклонена'};
const outcomes: Record<string, string> = {confirmed: 'Подтвердился', false: 'Ложный', monitoring: 'Мониторинг'};
const decision = (p: Row): Row | undefined => p.decision ?? (Array.isArray(p.decisions) ? p.decisions.at(-1) : undefined);
const operational = (p: Row) => p.incident_type !== 'intrusion_false_alarm' && p.role !== 'shadow';
const pending = (p: Row) => operational(p) && ['high', 'medium'].includes(p.risk) && !decision(p);

export function OperationsAnalytics({objects, predictions, recommendations, onPrediction, onWork}: Props) {
  const [objectId, setObjectId] = useState('');
  const heading = useRef<HTMLDivElement>(null);
  function selectSection(id: string) {setObjectId(id); heading.current?.scrollIntoView({block: 'start'}); heading.current?.focus({preventScroll: true});}
  const forecasts = predictions.filter(p => !objectId || String(p.object_id) === objectId);
  const works = recommendations.filter(w => !objectId || String(w.object_id) === objectId);
  const unresolved = forecasts.filter(pending).sort((a,b) => (a.risk === 'high' ? 0 : 1) - (b.risk === 'high' ? 0 : 1));
  const decisions = forecasts.filter(p => decision(p)).sort((a,b) => (Date.parse(decision(b)?.ts) || 0) - (Date.parse(decision(a)?.ts) || 0));
  const name = (id: string) => objects.find(o => String(o.id) === String(id))?.name ?? id;
  const sections = useMemo(() => objects.map(object => {
    const rows = predictions.filter(p => String(p.object_id) === String(object.id));
    return {object, pending: rows.filter(pending).length, decisions: rows.filter(p => decision(p)).length, open: recommendations.filter(w => String(w.object_id) === String(object.id) && ['new','accepted'].includes(w.data?.status)).length, assessed: rows.some(p => operational(p) && ['high','medium','low','normal'].includes(p.risk))};
  }).sort((a,b) => b.pending - a.pending || b.open - a.open), [objects, predictions, recommendations]);
  return <section className="operations-analytics" aria-labelledby="operations-title">
    <div className="oa-heading" ref={heading} tabIndex={-1} aria-label="Сводка выбранного участка"><div><span>ЭКСПЛУАТАЦИЯ / ТЕКУЩИЙ СРЕЗ</span><h2 id="operations-title">Что требует внимания</h2><p>Последние загруженные прогнозы и рекомендации. Это срез работы, а не статистика всех смен.</p></div><label>Участок<select value={objectId} onChange={e => setObjectId(e.target.value)}><option value="">Все загруженные · {objects.length}</option>{objects.map(o => <option key={o.id} value={o.id}>{o.name ?? o.id}</option>)}</select></label></div>
    <dl className="oa-totals"><div><dt>Высокий риск без решения</dt><dd>{unresolved.filter(p => p.risk === 'high').length}</dd></div><div><dt>Повышенный риск без решения</dt><dd>{unresolved.filter(p => p.risk === 'medium').length}</dd></div><div><dt>Прогнозов с решением</dt><dd>{decisions.length}</dd></div><div><dt>Открытых работ</dt><dd>{works.filter(w => ['new','accepted'].includes(w.data?.status)).length}</dd></div></dl>
    <div className="oa-columns"><section><h3>Очередь проверки <small>{unresolved.length}</small></h3>{unresolved.length ? unresolved.map(p => <button className="oa-record" key={p.id} onClick={() => onPrediction(p)}><span><strong>{name(p.object_id)}</strong><small>{incidentNames[p.incident_type] ?? p.incident_type} · {p.risk === 'high' ? 'Высокий риск' : 'Повышенный риск'}</small></span><ArrowUpRight size={18}/></button>) : <p className="oa-empty">В выбранных записях нет высоких или повышенных рисков без решения. Это не подтверждает отсутствие аварий.</p>}</section>
    <section><h3>Обслуживание <small>{works.length}</small></h3><div className="oa-work-status">{Object.entries(statuses).map(([key,label]) => <span key={key}>{label}<b>{works.filter(w => w.data?.status === key).length}</b></span>)}</div>{works.map(w => <button className="oa-record" key={w.id} onClick={() => onWork(String(w.id))}><span><strong>{name(w.object_id)}</strong><small>{w.data?.action ?? 'Действие не указано'}</small><small>{statuses[w.data?.status] ?? 'Статус неизвестен'}</small></span><ArrowUpRight size={18}/></button>)}{!works.length && <p className="oa-empty">Рекомендаций для выбранного участка нет в загруженных данных.</p>}</section></div>
    <section className="oa-section"><h3>По участкам</h3><p>Выберите участок, чтобы сузить сводку. Отсутствие оценки не считается нормой.</p><div className="table-scroll"><table><thead><tr><th>Участок</th><th>Без решения</th><th>С решением</th><th>Открыто работ</th><th>Оценка</th></tr></thead><tbody>{sections.filter(s => !objectId || String(s.object.id) === objectId).map(s => <tr key={s.object.id}><td><button onClick={() => selectSection(String(s.object.id))}>{s.object.name ?? s.object.id}</button></td><td>{s.pending}</td><td>{s.decisions}</td><td>{s.open}</td><td>{s.assessed ? 'Есть прогноз' : 'Нет оценки'}</td></tr>)}</tbody></table></div>{!objects.length && <p className="oa-empty">Справочник участков не загружен. Обновите данные рабочего места.</p>}</section>
    <section className="oa-section"><h3>Решения по прогнозам</h3><p>Последнее решение каждой загруженной записи. Полная история смен и назначение бригад в этом источнике отсутствуют.</p>{decisions.map(p => {const d=decision(p)!; return <button className="oa-record" key={p.id} onClick={() => onPrediction(p)}><span><strong>{name(p.object_id)} · {outcomes[d.outcome] ?? 'Результат не указан'}</strong><small>{d.username ?? 'Автор не передан'} · {d.ts && Number.isFinite(Date.parse(d.ts)) ? date(d.ts) : 'Время не передано'}</small>{d.comment && <span className="oa-comment">{d.comment}</span>}</span><ArrowUpRight size={18}/></button>})}{!decisions.length && <p className="oa-empty">Сохранённых решений в выбранных прогнозах нет.</p>}</section>
  </section>;
}
