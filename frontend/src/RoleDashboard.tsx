import {ArrowRight, ArrowUpRight, Check, ClipboardList, MessageSquareText, ScanLine, Wrench} from 'lucide-react';
import {useState} from 'react';
import {Row, date, incidentNames, riskNames} from './api';
import './role-workspaces.css';
import './role-approved.css';
import {NetworkOverview} from './NetworkOverview';

type Props = {
  role: string;
  username: string;
  objects: Row[];
  predictions: Row[];
  recommendations: Row[];
  objectName: (id: string) => string;
  onTab: (tab: string) => void;
  onWorkSelect: (id: string) => void;
  onSelect: (prediction: Row) => void;
};

const workStatus: Record<string, string> = {new: 'Новая', accepted: 'Принята', completed: 'Выполнена', rejected: 'Отклонена'};
const decisionStatus: Record<string, string> = {confirmed: 'Подтвердился', false: 'Ложный', monitoring: 'Мониторинг'};

function pct(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : 'нет оценки';
}

function kind(prediction: Row) {
  if (prediction.model_kind === 'rules') return 'Правила';
  if (prediction.model_kind === 'stub') return 'STUB';
  if (prediction.model_kind === 'ml') return `ML ${prediction.model_version ? 'v' + prediction.model_version : ''}`.trim();
  return 'Источник не указан';
}

function predictionName(prediction: Row) {
  return incidentNames[prediction.incident_type] ?? 'Тип не указан';
}

function latestTime(value: unknown) {
  return typeof value === 'string' && value ? date(value) : 'Время не указано';
}

function WorkRow({row, objectName, onOpen}: {row: Row; objectName: Props['objectName']; onOpen: () => void}) {
  return <button type="button" className="rw-list-row" onClick={onOpen}>
    <span className="rw-list-main"><strong>{objectName(row.object_id)}</strong><small>{row.data?.action ?? 'Действие не указано'}</small></span>
    <span className="rw-list-status">{workStatus[row.data?.status] ?? 'Статус не указан'}<ArrowUpRight size={15}/></span>
  </button>;
}

function PredictionRow({row, objectName, onOpen, showDecision = false}: {row: Row; objectName: Props['objectName']; onOpen: () => void; showDecision?: boolean}) {
  return <button type="button" className="rw-list-row" onClick={onOpen}>
    <span className="rw-list-main"><strong>{objectName(row.object_id)}</strong><small>{predictionName(row)} · {kind(row)} · {typeof row.horizon_h === 'number' ? `${row.horizon_h} ч` : 'Горизонт не указан'}</small></span>
    <span className="rw-list-status">{showDecision ? decisionStatus[row.decision?.outcome] ?? 'Решение есть' : pct(row.probability)}<ArrowUpRight size={15}/></span>
  </button>;
}

function TechnicianSchematic() {
  const zones = [
    {name: 'Кабельная полка', text: 'Сопоставьте обозначение оборудования в рекомендации и на объекте. Схема показывает типовое расположение, а не точную точку неисправности.'},
    {name: 'Датчик', text: 'Сверьте канал, время последнего показания и сообщение об ошибке. Порядок проверки определяется действующим регламентом и допуском.'},
    {name: 'Нижний ярус', text: 'Уточните расположение оборудования по документации объекта. Наличие воды на этой условной схеме не показано и не подтверждается.'},
  ];
  const [zone, setZone] = useState(1);
  return <section className="rw-schematic" aria-label="Условный разрез коллектора">
    <div className="rw-section-label"><span>Устройство участка</span><span>Условный разрез</span></div>
    <div className="rw-schematic-layout"><svg viewBox="0 0 340 220" role="img" aria-label="Схематический разрез: кабельная полка слева, датчик на своде, нижний ярус у пола">
      <path d="M57 195V89a113 73 0 0 1 226 0v106Z" fill="#edf5fc" stroke="#91a7cc" strokeWidth="10"/>
      <path d="M65 195h210" stroke="#41558d" strokeWidth="3"/>
      <path d="M72 111h58m-58 37h58m-17-37v20m0 17v20" fill="none" stroke={zone === 0 ? '#b45c24' : '#41558d'} strokeWidth="5"/>
      <circle cx="160" cy="60" r="11" fill={zone === 1 ? '#b45c24' : '#41558d'}/><path d="M160 71v29" stroke="#41558d" strokeWidth="2" strokeDasharray="4 4"/>
      <rect x="222" y="158" width="30" height="29" rx="3" fill={zone === 2 ? '#b45c24' : '#41558d'}/>
      <text x="81" y="95">01</text><text x="180" y="65">02</text><text x="218" y="146">03</text>
    </svg><div className="rw-schematic-zones" aria-label="Элементы разреза">{zones.map((item, index) => <button type="button" key={item.name} aria-pressed={zone === index} onClick={() => setZone(index)}><span>0{index + 1}</span>{item.name}<ArrowUpRight size={15}/></button>)}</div></div>
    <p aria-live="polite"><strong>{zones[zone].name}. </strong>{zones[zone].text}</p>
  </section>;
}

function TechnicianWorkspace({username, predictions, recommendations, objectName, onTab, onSelect, onWorkSelect}: Omit<Props, 'role'>) {
  const openWork = recommendations.filter(row => row.data?.status === 'new' || row.data?.status === 'accepted');
  const accepted = openWork.filter(row => row.data?.status === 'accepted');
  const current = accepted[0] ?? openWork[0];
  const sensor = predictions.filter(row => row.incident_type === 'sensor_failure').sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
  const otherWork = openWork.filter(row => row.id !== current?.id);
  return <section className="role-workspace rw rw-technician" aria-label="Рабочее место технического персонала">
    <header className="rw-head"><div><span className="rw-kicker">ТЕХНИЧЕСКИЙ ПЕРСОНАЛ / {username}</span><h2>Работы на участках</h2><p>Рекомендации, схема оборудования и результаты проверки.</p></div><Wrench aria-hidden="true" size={28}/></header>
    <div className="rw-strip" aria-label="Состояние работы"><span><b>{openWork.length}</b> открытых рекомендаций</span><span><b>{accepted.length}</b> принятых</span><span><b>{sensor.length}</b> прогнозов отказа датчика</span></div>
    <div className="rw-tech-grid">
      <div className="rw-main">
        <div className="rw-section-label"><span>01 / ТЕКУЩАЯ РАБОТА</span><span>{current ? workStatus[current.data?.status] ?? 'Статус не указан' : 'Нет записи'}</span></div>
        {current ? <div className="rw-feature">
          <span className="rw-object">{objectName(current.object_id)}</span>
          <h3>{current.data?.action ?? 'Действие не указано'}</h3>
          <div className="rw-facts"><span>Окно работ <b>{current.data?.window_from && current.data?.window_to ? `${latestTime(current.data.window_from)} — ${latestTime(current.data.window_to)}` : 'не назначено'}</b></span><span>Основание <b>{current.data?.schedule_comparison ?? 'сравнение с планом недоступно'}</b></span><span>Оценка риска <b>{pct(current.data?.rationale?.probability)}</b></span></div>
          <button type="button" className="rw-primary" onClick={() => onWorkSelect(current.id)}>Открыть работу и комментарии <ArrowRight size={17}/></button>
        </div> : <div className="rw-feature rw-feature-empty"><h3>Открытых рекомендаций нет</h3><p>Для этого среза рабочая запись не поступила. Историю и статусы можно открыть в разделе обслуживания.</p><button type="button" className="rw-secondary" onClick={() => onTab('recommendations')}>Открыть обслуживание <ArrowUpRight size={16}/></button></div>}
        <TechnicianSchematic/>
      </div>
      <div className="rw-route">
        <div className="rw-section-label"><span>02 / МАРШРУТ ПРОВЕРКИ</span><ScanLine size={17}/></div>
        <ol>
          <li className={current ? 'current' : ''}><b>01</b><span><strong>Прочитать рекомендацию</strong><small>Объект, основание, окно работ</small></span></li>
          <li className={current?.data?.status === 'accepted' ? 'current' : ''}><b>02</b><span><strong>Сверить показания</strong><small>Датчики, события, действующий регламент</small></span></li>
          <li><b>03</b><span><strong>Проверить на месте</strong><small>Только с допуском и по регламенту</small></span></li>
          <li><b>04</b><span><strong>Передать результат</strong><small>Комментарий и статус в карточке работы</small></span></li>
        </ol>
        <div className="rw-route-note"><MessageSquareText size={17}/><span>Комментарий сохраняется в разделе «Обслуживание». Прогноз сам по себе не является заданием на ремонт.</span></div>
      </div>
    </div>
    <div className="rw-bottom-grid"><section className="rw-queue" aria-label="Следующие рекомендации"><div className="rw-section-label"><span>ОЧЕРЕДЬ РАБОТ</span><button type="button" onClick={() => onTab('recommendations')}>Все работы <ArrowUpRight size={15}/></button></div>{otherWork.length ? otherWork.slice(0, 3).map(row => <WorkRow key={row.id} row={row} objectName={objectName} onOpen={() => onWorkSelect(row.id)}/>) : <p className="rw-empty">Других открытых рекомендаций нет.</p>}</section><section className="rw-queue" aria-label="Прогнозы отказа датчиков"><div className="rw-section-label"><span>ДАТЧИКИ / КОНТЕКСТ</span><span>{sensor.length} в срезе</span></div>{sensor.length ? sensor.slice(0, 3).map(row => <PredictionRow key={row.id} row={row} objectName={objectName} onOpen={() => onSelect(row)}/>) : <p className="rw-empty">Прогнозов отказа датчиков в загруженных данных нет.</p>}</section></div>
  </section>;
}

function ManagerWorkspace({username, objects, predictions, recommendations, objectName, onTab, onSelect, onWorkSelect}: Omit<Props, 'role'>) {
  const operational = predictions.filter(row => row.incident_type !== 'intrusion_false_alarm');
  const pending = operational.filter(row => row.risk === 'high' && !row.decision).sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
  const decided = operational.filter(row => row.decision);
  const openWork = recommendations.filter(row => row.data?.status === 'new' || row.data?.status === 'accepted');
  return <section className="role-workspace rw rw-manager" aria-label="Рабочее место руководителя">
    <header className="rw-head"><div><span className="rw-kicker">РУКОВОДИТЕЛЬ / {username}</span><h2>Обзор сети</h2><p>Риски, решения диспетчеров и обслуживание по загруженным объектам.</p></div><ClipboardList aria-hidden="true" size={28}/></header>
    <div className="rw-manager-lead"><div className="rw-lead-number"><strong>{pending.length}</strong><span>прогнозов высокого риска<br/>ожидают решения</span><button type="button" onClick={() => onTab('predictions')}>Открыть прогнозы <ArrowRight size={16}/></button></div><div className="rw-manager-status"><div><b>{openWork.length}</b><span>работ в очереди</span></div><div><b>{decided.length}</b><span>прогнозов с решением</span></div><p>Числа относятся к загруженным записям. Они не показывают эффективность модели или состояние всей сети.</p></div></div>
    <NetworkOverview objects={objects} predictions={predictions} recommendations={recommendations} onSelect={onSelect} onWorkSelect={onWorkSelect}/>
    <div className="rw-manager-grid"><section className="rw-queue" aria-label="Очередь решений"><div className="rw-section-label"><span>01 / ОЧЕРЕДЬ РЕШЕНИЙ</span><button type="button" onClick={() => onTab('predictions')}>Все прогнозы <ArrowUpRight size={15}/></button></div>{pending.length ? pending.slice(0, 4).map(row => <PredictionRow key={row.id} row={row} objectName={objectName} onOpen={() => onSelect(row)}/>) : <p className="rw-empty">Высоких прогнозов без решения в загруженных данных нет.</p>}</section><section className="rw-queue" aria-label="Очередь обслуживания"><div className="rw-section-label"><span>02 / ОБСЛУЖИВАНИЕ</span><button type="button" onClick={() => onTab('recommendations')}>Все работы <ArrowUpRight size={15}/></button></div>{openWork.length ? openWork.slice(0, 4).map(row => <WorkRow key={row.id} row={row} objectName={objectName} onOpen={() => onWorkSelect(row.id)}/>) : <p className="rw-empty">Открытых рекомендаций в загруженных данных нет.</p>}</section></div>
    <section className="rw-decisions" aria-label="Последние решения"><div className="rw-section-label"><span>03 / РЕШЕНИЯ ПО ПРОГНОЗАМ</span><span>человеческая проверка</span></div>{decided.length ? decided.slice(0, 4).map(row => <button type="button" key={row.id} onClick={() => onSelect(row)}><span>{objectName(row.object_id)}</span><span>{predictionName(row)}</span><strong>{decisionStatus[row.decision?.outcome] ?? 'Решение есть'}</strong><ArrowUpRight size={15}/></button>) : <p className="rw-empty">Решения диспетчера в этом срезе не сохранены.</p>}</section>
  </section>;
}

function AnalystWorkspace({username, predictions, objectName, onTab, onSelect}: Omit<Props, 'role' | 'recommendations'>) {
  const decided = predictions.filter(row => row.decision);
  const undecided = predictions.filter(row => !row.decision);
  const rules = predictions.filter(row => row.model_kind === 'rules');
  const stub = predictions.filter(row => row.model_kind === 'stub');
  return <section className="role-workspace rw rw-analyst" aria-label="Рабочее место аналитика">
    <header className="rw-head"><div><span className="rw-kicker">АНАЛИТИК / {username}</span><h2>Прогнозы и исходы</h2><p>Источник расчёта, решение диспетчера и ограничения оценки.</p></div><ScanLine aria-hidden="true" size={28}/></header>
    <div className="rw-analyst-strip"><span><b>{predictions.length}</b> прогнозов в срезе</span><span><b>{decided.length}</b> с решением</span><span><b>{undecided.length}</b> без решения</span></div>
    <div className="rw-analyst-grid"><section className="rw-analyst-main"><div className="rw-section-label"><span>01 / ЗАПИСИ ДЛЯ ПРОВЕРКИ</span><button type="button" onClick={() => onTab('predictions')}>Все прогнозы <ArrowUpRight size={15}/></button></div><div className="rw-analyst-list">{predictions.length ? predictions.slice(0, 6).map((row, index) => <button type="button" key={row.id} onClick={() => onSelect(row)}><span className="rw-index">{String(index + 1).padStart(2, '0')}</span><span className="rw-list-main"><strong>{objectName(row.object_id)}</strong><small>{predictionName(row)} · {latestTime(row.as_of)}</small></span><span className="rw-analytic-source">{kind(row)}<small>{riskNames[row.risk] ?? 'Риск не указан'} · {pct(row.probability)}</small></span><span className="rw-analytic-decision">{row.decision ? decisionStatus[row.decision.outcome] ?? 'Решение есть' : 'Без решения'}</span><ArrowUpRight size={15}/></button>) : <p className="rw-empty">Прогнозы не загружены.</p>}</div></section><aside className="rw-analyst-side"><div className="rw-section-label"><span>02 / ИСТОЧНИК И ОЦЕНКА</span></div><div className="rw-source-grid"><div><b>{rules.length}</b><span>по правилам</span></div><div><b>{stub.length}</b><span>STUB</span></div></div><p>Показанное решение диспетчера не равно подтверждённому фактическому исходу. По нему одному нельзя заявить точность модели.</p><div className="rw-quality"><Check size={18}/><span><strong>Проверить качество</strong><small>Метрики доступны только для размеченных исходов и завершённых горизонтов.</small></span></div><button type="button" className="rw-primary" onClick={() => onTab('quality')}>Открыть аналитику качества <ArrowRight size={17}/></button></aside></div>
  </section>;
}

export function RoleDashboard({role, ...props}: Props) {
  if (role === 'technician') return <TechnicianWorkspace {...props}/>;
  if (role === 'analyst') return <AnalystWorkspace {...props}/>;
  return <ManagerWorkspace {...props}/>;
}
