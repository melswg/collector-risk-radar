import {useState} from 'react';
import {date, Row} from './api';
import {eventPresentation} from './event-presentation';
import './event-journal.css';

export function EventJournal({rows, objectName}: {rows: Row[]; objectName: (id: string) => string}) {
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('all');
  const visible = rows.filter(row => {
    const search = query.trim().toLocaleLowerCase('ru');
    const matches = !search || [row.event, row.channel_id, objectName(row.object_id)].some(value => String(value ?? '').toLocaleLowerCase('ru').includes(search));
    return matches && (level === 'all' || eventPresentation(row.severity).tone === level);
  });
  return <section className="event-journal" aria-label="Журнал загруженных событий">
    <div className="ej-search"><label>Поиск в загруженных событиях<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Сообщение, участок или канал"/></label><label>Уровень события<select value={level} onChange={e => setLevel(e.target.value)}><option value="all">Все уровни</option><option value="critical">Критические и ошибки</option><option value="warning">Предупреждения</option><option value="info">Информация</option><option value="normal">Норма</option><option value="unknown">Уровень не указан</option></select></label></div>
    <p className="ej-count" role="status">Показано {visible.length} из {rows.length} загруженных событий. Серверная выборка ограничена 100 записями.</p>
    <div className="table-scroll"><table className="event-table"><thead><tr><th>Время регистрации</th><th>Объект</th><th>Канал датчика</th><th>Сообщение</th><th>Уровень и контекст</th></tr></thead><tbody>{visible.map(row => {const status=eventPresentation(row.severity); return <tr key={row.id}><td className="mono">{row.ts && Number.isFinite(Date.parse(row.ts)) ? date(row.ts) : 'Время не передано'}</td><td data-label="Объект">{objectName(row.object_id)}</td><td data-label="Канал">{row.channel_id != null && row.channel_id !== '—' ? `№ ${row.channel_id}` : 'Не указан'}</td><td data-label="Сообщение">{row.event || 'Сообщение не передано'}</td><td data-label="Уровень и контекст"><span className={`ej-level ej-${status.tone}`}>{status.label}</span>{row.expected && <small className="ej-expected">В период плановых работ</small>}</td></tr>})}</tbody></table></div>
    {!visible.length && <div className="ej-empty"><h3>{rows.length ? 'Совпадений нет' : 'События не загружены'}</h3><p>{rows.length ? 'Измените текст поиска или уровень события.' : 'Проверьте период и объект в фильтрах выше, затем нажмите «Применить».'}</p>{rows.length > 0 && <button onClick={() => {setQuery(''); setLevel('all');}}>Сбросить поиск и уровень</button>}</div>}
  </section>;
}
