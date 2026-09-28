import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {ArrowUpRight, Grip, RotateCcw, X} from 'lucide-react';
import {Row, incidentNames, riskNames, date} from './api';
import './companion-role.css';
import './approved-companion.css';

type Character = 'mole' | 'beaver' | 'fox';
type Point = {x: number; y: number};
type Props = {
  predictions: Row[];
  notifications: Row[];
  username: string;
  role: string;
  objectName: (id: string) => string;
  onSelect: (prediction: Row) => void;
  onOpenNotification: (notification: Row) => void;
};

const characters: Record<Character, {name: string; image: string}> = {
  mole: {name: 'Крот', image: '/collector-mole.webp'},
  beaver: {name: 'Бобёр', image: '/collector-beaver.webp'},
  fox: {name: 'Лиса', image: '/collector-fox.webp'},
};

function savedCharacter(): Character {
  try {
    const saved = localStorage.getItem('collector-companion-character');
    return saved === 'mole' || saved === 'beaver' || saved === 'fox' ? saved : 'mole';
  } catch {return 'mole';}
}

function savedPosition(): Point | null {
  try {
    const raw = localStorage.getItem('collector-companion-position');
    if (!raw) return null;
    const point = JSON.parse(raw);
    return Number.isFinite(point.x) && Number.isFinite(point.y) ? point : null;
  } catch {return null;}
}

const roleNames: Record<string, string> = {dispatcher: 'Диспетчер', technician: 'Технический персонал', manager: 'Руководитель', analyst: 'Аналитик', admin: 'Администратор'};

function percent(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : 'нет оценки';
}

function source(prediction: Row) {
  if (prediction.model_kind === 'rules') return 'Правила';
  if (prediction.model_kind === 'stub') return 'STUB';
  return prediction.model_kind === 'ml' ? 'Модель' : 'Источник не указан';
}

function detail(prediction: Row, objectName: Props['objectName']) {
  const name = incidentNames[prediction.incident_type] ?? 'Прогноз';
  const risk = riskNames[prediction.risk] ?? 'Уровень не указан';
  const horizon = Number.isFinite(prediction.horizon_h) ? ` · ${prediction.horizon_h} ч` : '';
  return `${name} · ${objectName(prediction.object_id)} · ${risk} · ${percent(prediction.probability)}${horizon} · ${source(prediction)}`;
}

export function SignalCompanion({predictions, notifications, username, role, objectName, onSelect, onOpenNotification}: Props) {
  const [open, setOpen] = useState(false);
  const [character, setCharacter] = useState<Character>(savedCharacter);
  const [position, setPosition] = useState<Point | null>(savedPosition);
  const trigger = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [cardPosition, setCardPosition] = useState<Point>({x: 8, y: 8});
  const container = useRef<HTMLElement>(null);
  const drag = useRef<{pointerId: number; startX: number; startY: number; originX: number; originY: number; lastX: number; lastY: number; moved: boolean} | null>(null);
  const ignoreClick = useRef(false);
  const high = predictions.filter(p => p.incident_type !== 'intrusion_false_alarm' && p.risk === 'high');
  const medium = predictions.filter(p => p.incident_type !== 'intrusion_false_alarm' && p.risk === 'medium');
  const unread = notifications.filter(n => !n.data?.read_by?.includes(username));
  const state = high.length || unread.length ? 'alert' : medium.length ? 'watch' : 'calm';
  const ranked = [...high, ...medium].filter(p => !p.decision).sort((a,b) => (b.probability ?? -1) - (a.probability ?? -1));
  const technical = [...predictions].sort((a,b) => Number(b.incident_type === 'sensor_failure') - Number(a.incident_type === 'sensor_failure') || (b.probability ?? -1) - (a.probability ?? -1));
  const sensorForecasts = technical.filter(p => p.incident_type === 'sensor_failure' && ['high', 'medium'].includes(p.risk));
  const isDispatcher = role === 'dispatcher' || role === 'admin';
  const isTechnician = role === 'technician';
  const isManager = role === 'manager';
  const heading = isDispatcher ? 'Сигналы смены' : isTechnician ? 'Технический разбор' : isManager ? 'Обзор рисков' : 'Данные по прогнозам';
  const status = isDispatcher ? (unread.length ? `${unread.length} новых уведомлений` : high.length ? `${high.length} высоких рисков` : 'Новых уведомлений нет')
    : isTechnician ? (sensorForecasts.length ? `${sensorForecasts.length} сигнала по датчикам` : 'Нет приоритетных сигналов по датчикам')
    : isManager ? `${high.length} высоких · ${medium.length} повышенных` : `${predictions.length} прогнозов`;

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = trigger.current?.getBoundingClientRect();
      const panel = card.current?.getBoundingClientRect();
      if (!anchor || !panel) return;
      setCardPosition({
        x: Math.max(8, Math.min(anchor.left, window.innerWidth - panel.width - 8)),
        y: Math.max(8, Math.min(anchor.top - panel.height - 12, window.innerHeight - panel.height - 8)),
      });
    };
    place();
    const observer = new ResizeObserver(place);
    if (card.current) observer.observe(card.current);
    window.addEventListener('resize', place);
    return () => {observer.disconnect(); window.removeEventListener('resize', place);};
  }, [open, position]);

  useEffect(() => {if (open) closeButton.current?.focus();}, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {setOpen(false); trigger.current?.focus();}
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  useEffect(() => {
    const clamp = () => {
      const bounds = trigger.current?.getBoundingClientRect();
      setPosition(old => old && ({x: Math.max(8, Math.min(old.x, window.innerWidth - (bounds?.width ?? 72) - 8)), y: Math.max(8, Math.min(old.y, window.innerHeight - (bounds?.height ?? 72) - 8))}));
    };
    window.addEventListener('resize', clamp);
    clamp();
    return () => window.removeEventListener('resize', clamp);
  }, []);

  function choose(next: Character) {
    setCharacter(next);
    try {localStorage.setItem('collector-companion-character', next);} catch { /* storage optional */ }
  }

  function resetPosition() {
    setPosition(null);
    try {localStorage.removeItem('collector-companion-position');} catch { /* storage optional */ }
  }

  function onPointerDown(event: React.PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || !event.isPrimary) return;
    ignoreClick.current = false;
    const rect = container.current?.getBoundingClientRect();
    if (!rect) return;
    drag.current = {pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: rect.left, originY: rect.top, lastX: event.clientX, lastY: event.clientY, moved: false};
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: React.PointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;
    if (!current.moved && Math.hypot(dx, dy) < 6) return;
    current.moved = true;
    if (open) setOpen(false);
    current.lastX = event.clientX;
    current.lastY = event.clientY;
    const width = container.current?.getBoundingClientRect().width ?? 180;
    const height = container.current?.getBoundingClientRect().height ?? 80;
    setPosition({x: Math.max(8, Math.min(current.originX + dx, window.innerWidth - width - 8)), y: Math.max(8, Math.min(current.originY + dy, window.innerHeight - height - 8))});
  }

  function onPointerUp(event: React.PointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    if (current.moved) {
      ignoreClick.current = true;
      const width = container.current?.getBoundingClientRect().width ?? 180;
      const height = container.current?.getBoundingClientRect().height ?? 80;
      const next = {
        x: Math.max(8, Math.min(current.originX + current.lastX - current.startX, window.innerWidth - width - 8)),
        y: Math.max(8, Math.min(current.originY + current.lastY - current.startY, window.innerHeight - height - 8)),
      };
      setPosition(next);
      try {localStorage.setItem('collector-companion-position', JSON.stringify(next));} catch { /* storage optional */ }
    }
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function onTriggerClick(event: React.MouseEvent<HTMLButtonElement>) {
    if (ignoreClick.current && event.detail !== 0) {ignoreClick.current = false; return;}
    ignoreClick.current = false;
    setOpen(value => !value);
  }

  function moveWithKeyboard(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!event.altKey || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const next = {x: Math.max(8, Math.min(rect.left + (event.key === 'ArrowLeft' ? -24 : event.key === 'ArrowRight' ? 24 : 0), window.innerWidth - rect.width - 8)), y: Math.max(8, Math.min(rect.top + (event.key === 'ArrowUp' ? -24 : event.key === 'ArrowDown' ? 24 : 0), window.innerHeight - rect.height - 8))};
    setPosition(next);
    try {localStorage.setItem('collector-companion-position', JSON.stringify(next));} catch { /* storage optional */ }
  }

  function openPrediction(prediction: Row) {onSelect(prediction); setOpen(false);}

  return <aside ref={container} className={'companion companion-role '+state+(position ? ' companion-moved' : '')} style={position ? {left: position.x, top: position.y, right: 'auto', bottom: 'auto'} : undefined} aria-label="Помощник по сигналам">
    {open && <section ref={card} id="signal-companion-panel" className="companion-card" role="dialog" aria-label={heading} style={{left: cardPosition.x, top: cardPosition.y, right: 'auto', bottom: 'auto'}}>
      <div className="companion-heading"><span>{heading}<small>{roleNames[role] ?? 'Просмотр'}</small></span><button ref={closeButton} type="button" aria-label="Закрыть помощника" onClick={() => {setOpen(false); trigger.current?.focus();}}><X size={17}/></button></div>
      <div className="companion-picker" role="group" aria-label="Выбор персонажа">{(Object.keys(characters) as Character[]).map(key => <button type="button" key={key} aria-pressed={character === key} onClick={() => choose(key)}><img src={characters[key].image} alt="" width="1024" height="1536"/><span>{characters[key].name}</span></button>)}</div>
      <div className="companion-chat" aria-live="polite">
        <p className="companion-bubble companion-bubble-intro">{username ? `${username}, ` : ''}{heading}. Показываю данные, доступные в рабочем месте.</p>
        {isDispatcher && <>
          <p className="companion-bubble">{status}. {high.length ? 'Проверьте приоритетный прогноз и сохраните решение в карточке.' : 'Прогнозы высокого риска не показаны.'}</p>
          {unread.slice(0, 3).map(n => <button type="button" className="companion-chat-action" key={n.id} onClick={() => {onOpenNotification(n); setOpen(false);}}><span className="signal-notification-dot"/><span><b>{incidentNames[n.data?.incident_type] ?? 'Уведомление'} · {objectName(n.object_id)}</b><small>{n.ts ? date(n.ts) : 'Время не указано'} · {percent(n.data?.probability)} · Открыть уведомление</small></span><ArrowUpRight size={16}/></button>)}
          {ranked[0] && <button type="button" className="companion-chat-action" onClick={() => openPrediction(ranked[0])}><span><b>Приоритетный прогноз</b><small>{detail(ranked[0], objectName)}</small></span><ArrowUpRight size={16}/></button>}
          <p className="companion-bubble companion-bubble-note">Решение по прогнозу принимает диспетчер. Помощник не управляет оборудованием.</p>
        </>}
        {isTechnician && <>
          <p className="companion-bubble">Назначенные вам работы: данные о назначениях не подключены. Прогноз не является заданием на ремонт.</p>
          {sensorForecasts.length ? sensorForecasts.slice(0, 2).map(p => <button type="button" className="companion-chat-action" key={p.id} onClick={() => openPrediction(p)}><span><b>Прогноз отказа датчика</b><small>{detail(p, objectName)}</small><small>Открыть карточку и сверить показания датчиков</small></span><ArrowUpRight size={16}/></button>) : <p className="companion-bubble companion-bubble-note">Приоритетных прогнозов отказа датчика нет в загруженных данных.</p>}
        </>}
        {isManager && <>
          <p className="companion-bubble">В загруженных прогнозах: высокий риск — {high.length}, повышенный — {medium.length}. Непрочитанных уведомлений у вас — {unread.length}.</p>
          {ranked.length ? ranked.slice(0, 2).map(p => <button type="button" className="companion-chat-action" key={p.id} onClick={() => openPrediction(p)}><span><b>Объект под наблюдением</b><small>{detail(p, objectName)}</small></span><ArrowUpRight size={16}/></button>) : <p className="companion-bubble companion-bubble-note">Прогнозов высокого и повышенного риска нет в загруженных данных.</p>}
          <p className="companion-bubble companion-bubble-note">Оценка эффективности здесь недоступна: этот виджет не получает проверенные метрики.</p>
        </>}
        {!isDispatcher && !isTechnician && !isManager && <p className="companion-bubble">{status}. {ranked[0] ? 'Откройте прогноз для подробного разбора.' : 'Прогнозов высокого и повышенного риска нет в загруженных данных.'}</p>}
        {!isDispatcher && !isTechnician && !isManager && ranked[0] && <button type="button" className="companion-chat-action" onClick={() => openPrediction(ranked[0])}><span><b>Прогноз</b><small>{detail(ranked[0], objectName)}</small></span><ArrowUpRight size={16}/></button>}
      </div>
      <div className="companion-footer"><button type="button" className="companion-reset" onClick={resetPosition}><RotateCcw size={14}/> Вернуть в угол</button><small>Данные демонстрационного стенда</small></div>
    </section>}
    <span id="companion-move-hint" className="companion-sr-only">Перетащите фигурку мышью или используйте Alt и клавиши со стрелками. Enter открывает помощника.</span>
    <button type="button" className="companion-trigger" ref={trigger} aria-label={`${characters[character].name}: ${status}. Открыть помощника или перетащить`} aria-describedby="companion-move-hint" aria-controls={open ? 'signal-companion-panel' : undefined} aria-expanded={open} onKeyDown={moveWithKeyboard} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onLostPointerCapture={onPointerUp} onDragStart={event => event.preventDefault()} onClick={onTriggerClick}>
      <span className="companion-robot"><img src={characters[character].image} alt="" draggable={false} width="1024" height="1536"/></span>
      <span className="companion-caption"><strong>{characters[character].name}</strong><small>{isDispatcher && unread.length ? `${unread.length} новых` : isManager ? `${high.length} высоких` : isTechnician ? 'разбор' : 'на связи'}</small></span>
      <Grip className="companion-grip" size={14} aria-hidden="true"/>
      {isDispatcher && unread.length > 0 && <span className="companion-count" aria-hidden="true">{unread.length > 9 ? '9+' : unread.length}</span>}
    </button>
  </aside>;
}
