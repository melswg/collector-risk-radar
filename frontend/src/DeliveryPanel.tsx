import {useEffect, useRef, useState} from 'react';
import {Mail, MessageSquare, Send} from 'lucide-react';
import {api, Row, date, isDemoMode} from './api';

const channels = {telegram: ['Telegram', Send], email: ['Email', Mail], sms: ['SMS', MessageSquare]} as const;
const states: Record<string,string> = {disabled:'Отключён', unconfigured:'Нужна настройка', ready:'Готов к отправке', pending:'В очереди', retry:'Повтор ожидается', sending:'Отправляется', accepted:'Принято провайдером', uncertain:'Нужна сверка с провайдером', failed:'Ошибка', cancelled:'Отменено'};

export function DeliveryPanel() {
  const [status, setStatus] = useState<Row[]>([]), [outbox, setOutbox] = useState<Row[]>([]), [employees, setEmployees] = useState<Row[]>([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true), [loaded, setLoaded] = useState(false);
  const request = useRef(0);
  async function load() {
    const current = ++request.current;
    setLoading(true); setError(''); setConfirmed(false);
    try {
      const [s, o, u] = await Promise.all([api('/notification-delivery/status'), api('/notification-delivery/outbox'), api('/admin/users')]);
      if (!Array.isArray(s.channels) || !Array.isArray(o.items)) throw new Error('Сервис вернул неизвестный формат. Повторите загрузку.');
      if (current === request.current) {setStatus(s.channels); setOutbox(o.items); setEmployees(Array.isArray(u) ? u : []); setLoaded(true);}
    } catch (error) {
      if (current === request.current) {setLoaded(false); setError(error instanceof Error ? error.message : 'Статусы не загружены. Повторите запрос.');}
    } finally {if (current === request.current) setLoading(false);}
  }
  useEffect(() => {void load(); return () => {request.current++;};}, []);
  async function send(channel?: string) {
    if (isDemoMode || !loaded || loading || busy || !confirmed) return;
    setBusy(true); setError('');
    try {
      await api('/notification-delivery/' + (channel ? 'test' : 'dispatch'), channel ? {channel, confirm_send:true, request_id:crypto.randomUUID()} : {confirm_send:true, limit:20});
      await load(); setConfirmed(false);
    } catch(e) {setError(String(e));} finally {setBusy(false);}
  }
  return <section className="panel padded delivery-panel">
    <span className="eyebrow">ВНЕШНИЕ УВЕДОМЛЕНИЯ</span>
    <h2>Сигнал там, где находится команда</h2>
    <p>Telegram, SMS и email используют получателей, заданных администратором на сервере. Принятие сообщения провайдером ещё не подтверждает доставку человеку.</p>
    {isDemoMode && <p className="source-note">Демонстрация интерфейса. Каналы отключены, сообщения не отправляются.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {loading && <p role="status">Загружаем каналы и очередь…</p>}
    <div className="delivery-channels">{loaded && !loading && status.map(s => {
      const known = Object.hasOwn(channels, s.channel);
      const [title, Icon] = known ? channels[s.channel as keyof typeof channels] : [String(s.channel ?? 'Неизвестный канал'), MessageSquare];
      return <article key={s.channel}><Icon size={22}/><h3>{title}</h3><span className={'badge '+(s.state==='ready'?'normal':'insufficient')}>{states[s.state] ?? s.state}</span>
        <p>{s.state==='ready'?'Получатель настроен':s.state==='disabled'?'Отправка выключена в настройках сервера':'Администратору нужно завершить подключение'}</p>
        <button disabled={isDemoMode || !known || busy || !confirmed || s.state!=='ready'} onClick={() => void send(s.channel)}>Тестовое сообщение</button>
      </article>;
    })}</div>
    <label className="check"><input type="checkbox" disabled={isDemoMode || loading || !loaded || busy} checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>Отправить реальные сообщения настроенным получателям</label>
    <div className="toolbar"><button className="primary" disabled={isDemoMode || loading || !loaded || busy || !confirmed || !outbox.some(o => ['pending','retry'].includes(o.status))} onClick={() => void send()}>Отправить очередь</button><button disabled={busy || loading} onClick={() => void load()}>Обновить статусы</button></div>
    <p className="muted">В этой версии отправку запускает администратор. Неопределённый результат требует сверки с провайдером перед повтором.</p>
    {loaded && !loading && (outbox.length ? <div className="table-scroll"><table><thead><tr><th>Канал</th><th>Состояние</th><th>Попытки</th><th>Обновлено</th></tr></thead><tbody>{outbox.map(o => <tr key={o.id}><td>{Object.hasOwn(channels,o.channel)?channels[o.channel as keyof typeof channels][0]:o.channel??'Не указан'}</td><td>{states[o.status] ?? o.status ?? 'Не указано'}</td><td>{o.attempts??'Не передано'}</td><td>{o.updated_at&&Number.isFinite(Date.parse(o.updated_at))?date(o.updated_at):'Не передано'}</td></tr>)}</tbody></table></div> : <p className="muted">{isDemoMode?'В демо нет очереди внешних сообщений.':'В загруженной очереди нет сообщений. Наполнение зависит от настроек каналов и правил сервиса.'}</p>)}
    <h3>Привязка Telegram у сотрудников</h3>
    {loaded && !loading && (employees.length ? <div className="table-scroll"><table><thead><tr><th>Сотрудник</th><th>Роль</th><th>Telegram</th></tr></thead><tbody>{employees.map(u => <tr key={u.username}><td>{u.username}</td><td>{u.role}</td><td>{u.telegram_linked ? (u.telegram_enabled ? `Привязан · ${u.telegram_chat_id}` : `Привязан, отключён · ${u.telegram_chat_id}`) : 'Не привязан'}</td></tr>)}</tbody></table></div> : <p className="muted">Список сотрудников не загружен.</p>)}
  </section>;
}
