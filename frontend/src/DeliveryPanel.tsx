import {useEffect, useState} from 'react';
import {Mail, MessageSquare, Send} from 'lucide-react';
import {api, Row, date} from './api';

const channels = {telegram: ['Telegram', Send], email: ['Email', Mail], sms: ['SMS', MessageSquare]} as const;
const states: Record<string,string> = {disabled:'Отключён', unconfigured:'Нужна настройка', ready:'Готов к отправке', pending:'В очереди', retry:'Повтор ожидается', sending:'Отправляется', accepted:'Принято провайдером', uncertain:'Нужна сверка с провайдером', failed:'Ошибка', cancelled:'Отменено'};

export function DeliveryPanel() {
  const [status, setStatus] = useState<Row[]>([]), [outbox, setOutbox] = useState<Row[]>([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [confirmed, setConfirmed] = useState(false);
  async function load() {
    const [s, o] = await Promise.all([api('/notification-delivery/status'), api('/notification-delivery/outbox')]);
    setStatus(s.channels); setOutbox(o.items);
  }
  useEffect(() => {load().catch(e => setError(String(e)));}, []);
  async function send(channel?: string) {
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
    {error && <p className="error" role="alert">{error}</p>}
    <div className="delivery-channels">{status.map(s => {
      const [title, Icon] = channels[s.channel as keyof typeof channels];
      return <article key={s.channel}><Icon size={22}/><h3>{title}</h3><span className={'badge '+(s.state==='ready'?'normal':'insufficient')}>{states[s.state] ?? s.state}</span>
        <p>{s.state==='ready'?'Получатель настроен':s.state==='disabled'?'Отправка выключена в настройках сервера':'Администратору нужно завершить подключение'}</p>
        <button disabled={busy || !confirmed || s.state!=='ready'} onClick={() => void send(s.channel)}>Тестовое сообщение</button>
      </article>;
    })}</div>
    <label className="check"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>Отправить реальные сообщения настроенным получателям</label>
    <div className="toolbar"><button className="primary" disabled={busy || !confirmed || !outbox.some(o => ['pending','retry'].includes(o.status))} onClick={() => void send()}>Отправить очередь</button><button disabled={busy} onClick={() => void load().catch(e => setError(String(e)))}>Обновить статусы</button></div>
    <p className="muted">В этой версии отправку запускает администратор. Неопределённый результат требует сверки с провайдером перед повтором.</p>
    {outbox.length ? <div className="table-scroll"><table><thead><tr><th>Канал</th><th>Состояние</th><th>Попытки</th><th>Обновлено</th></tr></thead><tbody>{outbox.map(o => <tr key={o.id}><td>{channels[o.channel as keyof typeof channels][0]}</td><td>{states[o.status] ?? o.status}</td><td>{o.attempts}</td><td>{date(o.updated_at)}</td></tr>)}</tbody></table></div> : <p className="muted">Очередь пуста. Новые уведомления высокого риска попадут сюда после включения каналов.</p>}
  </section>;
}
