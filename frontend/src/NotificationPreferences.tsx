import {useEffect, useState} from 'react';
import {Bell, Mail, MessageSquare, Send, X} from 'lucide-react';
import {api, isDemoMode} from './api';
import {useModalFocus} from './useModalFocus';
import './notification-preferences.css';

type Preferences = {telegram:boolean; sms:boolean; email:boolean; red:boolean; yellow:boolean};
const defaults:Preferences = {telegram:true,sms:false,email:false,red:true,yellow:true};
const channels = [{key:'telegram',name:'Telegram',Icon:Send},{key:'sms',name:'SMS',Icon:MessageSquare},{key:'email',name:'Email',Icon:Mail}] as const;
const storageKey = (username:string) => `moscollector-notification-draft-v1:${encodeURIComponent(username)}`;
function readPreferences(username:string):Preferences {
  try {
    const value=JSON.parse(localStorage.getItem(storageKey(username))??'null');
    if(value?.version===1)return Object.fromEntries(Object.entries(defaults).map(([key,fallback])=>[key,typeof value.preferences?.[key]==='boolean'?value.preferences[key]:fallback])) as Preferences;
  } catch { /* Invalid or unavailable storage leaves an editable draft. */ }
  return {...defaults};
}
const roleNames:Record<string,string>={dispatcher:'Диспетчер',technician:'Технический специалист',manager:'Руководитель',analyst:'Аналитик',admin:'Администратор'};
const examples:Record<string,[string,string]>={
  dispatcher:['Пресня, участок 14: высокий прогноз риска пожара. Проверьте время сигнала, показания и камеру. Решение ещё не принято.','Даниловский, участок 07: повышенный прогноз риска подтопления. Участок добавлен в очередь проверки.'],
  technician:['По работе на участке Пресня появился высокий прогноз риска. Уточните задание у диспетчера и действующий допуск до начала работ.','Даниловский, участок 07: добавлен комментарий диспетчера к проверке показаний. Откройте рабочую карточку и схему.'],
  manager:['По городу: один участок с высоким прогнозом риска. Проверка ещё не завершена. Откройте сводку участков и очередь решений.','В очереди профилактических работ появился участок с повышенным риском. Откройте сводку состояния работ.'],
  analyst:['Высокий прогноз риска на участке Пресня: демо-правила, горизонт 24 часа. Сопоставьте факторы прогноза и решение диспетчера.','Повышенный прогноз риска на участке Даниловский. Проверьте полноту показаний и источник оценки.'],
  admin:['Высокий прогноз риска в демонстрационном примере. Проверьте источник, журнал уведомлений и доступность рабочего места.','Новый сигнал повышенного риска в демонстрационном примере. Проверьте журнал и настройки сервиса.'],
};

type TelegramStatus = {linked: boolean; enabled: boolean; chat_id: string | null};
const telegramErrorText = (error: unknown) => error instanceof Error ? error.message : 'Запрос не выполнен. Повторите попытку.';

function TelegramLinkSection({username}: {username: string}) {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [deepLink, setDeepLink] = useState<{url: string; minutes: number} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');

  async function load() {
    try {setStatus(await api<TelegramStatus>('/telegram/status'));} catch (e) {setError(telegramErrorText(e));}
  }
  useEffect(() => {if (!isDemoMode) void load();}, []);

  async function requestLink() {
    setBusy(true); setError(''); setNotice('');
    try {
      const r = await api<{deep_link: string; expires_in_minutes: number}>('/telegram/link/token', {});
      setDeepLink({url: r.deep_link, minutes: r.expires_in_minutes});
    } catch (e) {setError(telegramErrorText(e));} finally {setBusy(false);}
  }
  async function toggle(enabled: boolean) {
    setBusy(true); setError('');
    try {setStatus(await api<TelegramStatus>('/telegram/status', {enabled}, 'PUT'));} catch (e) {setError(telegramErrorText(e));} finally {setBusy(false);}
  }
  async function unlink() {
    setBusy(true); setError(''); setNotice('');
    try {await api('/telegram/unlink', {}); setDeepLink(null); await load(); setNotice('Привязка Telegram удалена.');} catch (e) {setError(telegramErrorText(e));} finally {setBusy(false);}
  }

  return <fieldset className="np-telegram"><legend>Telegram-бот</legend>
    {isDemoMode ? <p className="source-note">Привязка Telegram недоступна в демонстрации интерфейса.</p> : <>
      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p role="status" className="np-message">{notice}</p>}
      {!status ? <p role="status">Загружаем статус привязки…</p> : status.linked ? <>
        <p>Telegram привязан · chat_id {status.chat_id}.</p>
        <label className="np-risk"><input type="checkbox" disabled={busy} checked={status.enabled} onChange={e => void toggle(e.target.checked)}/><span>Получать чрезвычайные сообщения в Telegram</span></label>
        <button type="button" disabled={busy} onClick={() => void unlink()}>Отвязать Telegram</button>
      </> : <>
        <p>Telegram не привязан к аккаунту сотрудника «{username}».</p>
        {deepLink ? <p>Ссылка действительна {deepLink.minutes} минут. Откройте её в Telegram и нажмите «Запустить»: <a href={deepLink.url} target="_blank" rel="noreferrer">{deepLink.url}</a></p>
          : <button type="button" disabled={busy} onClick={() => void requestLink()}>Получить ссылку для привязки Telegram</button>}
      </>}
    </>}
  </fieldset>;
}

export function NotificationPreferences({username,role,onClose}:{username:string;role:string;onClose:()=>void}) {
  const [preferences,setPreferences]=useState(()=>readPreferences(username));
  const [previewRisk,setPreviewRisk]=useState<'red'|'yellow'>('red');
  const [message,setMessage]=useState(''),[error,setError]=useState('');
  useModalFocus(true,'.notification-preferences');
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.stopPropagation();onClose()}};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[onClose]);
  function update(key:keyof Preferences,value:boolean){setPreferences(old=>({...old,[key]:value}));setMessage('');setError('')}
  function save(){try{localStorage.setItem(storageKey(username),JSON.stringify({version:1,preferences}));setMessage('Черновик сохранён в этом браузере. Сообщения не отправлялись.');setError('')}catch{setError('Не удалось сохранить черновик: хранилище браузера недоступно.');setMessage('')}}
  const selectedChannels=channels.filter(channel=>preferences[channel.key]);
  return <div className="overlay preferences-overlay" onClick={onClose}><section className="drawer notification-preferences" role="dialog" aria-modal="true" aria-labelledby="notification-preferences-title" onClick={event=>event.stopPropagation()}>
    <div className="np-top"><span><Bell size={18}/>Личные предпочтения</span><button type="button" aria-label="Закрыть настройки уведомлений" onClick={onClose}><X size={20}/></button></div>
    <h2 id="notification-preferences-title">Настройки уведомлений</h2>
    <p className="np-account">{username} · {roleNames[role]??role}</p>
    <TelegramLinkSection username={username}/>
    <p className="np-draft">Черновик в этом браузере, каналы ниже ещё не подключены.</p>
    <p className="np-intro">Выберите каналы и сигналы для будущего подключения. Здесь не запрашиваются контакты, токены или разрешение на отправку.</p>
    <form onSubmit={event=>{event.preventDefault();save()}}>
      <fieldset><legend>Куда получать</legend><div className="np-channels">{channels.map(({key,name,Icon})=><label key={key}><Icon size={19}/><span>{name}<small>Предпочтение, без подключения</small></span><input type="checkbox" checked={preferences[key]} onChange={event=>update(key,event.target.checked)}/></label>)}</div></fieldset>
      <fieldset><legend>Какие сигналы</legend><label className="np-risk"><input type="checkbox" checked={preferences.red} onChange={event=>update('red',event.target.checked)}/><span><b>Красные · высокий риск</b><small>Приоритетная проверка. Прогноз сам по себе не подтверждает аварию.</small></span></label><label className="np-risk"><input type="checkbox" checked={preferences.yellow} onChange={event=>update('yellow',event.target.checked)}/><span><b>Жёлтые · повышенный риск</b><small>Сигналы для уточнения и планирования проверки.</small></span></label></fieldset>
      <section className="np-preview" aria-label="Предпросмотр уведомления"><div className="np-preview-heading"><h3>Пример для вашей роли</h3><select aria-label="Тип примера уведомления" value={previewRisk} onChange={event=>setPreviewRisk(event.target.value as 'red'|'yellow')}><option value="red">Красный сигнал</option><option value="yellow">Жёлтый сигнал</option></select></div><small>ВЫМЫШЛЕННЫЕ ДАННЫЕ · {roleNames[role]??role}</small><p>{(examples[role]??examples.dispatcher)[previewRisk==='red'?0:1]}</p><div className="np-preview-summary">{!selectedChannels.length?'Каналы не выбраны.':!preferences[previewRisk]?'Этот тип сигнала выключен в черновике.':`Выбранные каналы: ${selectedChannels.map(c=>c.name).join(', ')}.`} Сообщение не отправляется.</div></section>
      {message&&<p role="status" className="np-message">{message}</p>}{error&&<p role="alert" className="error">{error}</p>}
      <div className="np-actions"><button type="button" onClick={onClose}>Закрыть</button><button type="submit" className="primary">Сохранить черновик</button></div>
    </form>
  </section></div>;
}
