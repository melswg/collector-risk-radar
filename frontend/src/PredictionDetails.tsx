import {useEffect, useRef, useState} from 'react';
import {ArrowRight, RefreshCw, X} from 'lucide-react';
import {DeferredChart} from './DeferredChart';
import {api, date, incidentNames, isDemoMode, riskNames, Row} from './api';
import {useModalFocus} from './useModalFocus';
import './prediction-details.css';

type Props = {
  p: Row;
  objectName: (id: string) => string;
  onClose: () => void;
  settings: Row;
  act: (f: () => Promise<unknown>, message?: string) => Promise<void>;
  canDecide: boolean;
  canSimulate: boolean;
};
type LoadState = 'loading' | 'ready' | 'error';
const outcomes: Record<string, string> = {confirmed: 'Подтвердился', false: 'Ложный', monitoring: 'Мониторинг'};
const channelNames: Record<string, string> = {temperature: 'Температура', water_level: 'Уровень воды', gas: 'Газ', smoke: 'Дым', humidity: 'Влажность', intrusion: 'Контроль доступа'};
const list = (value: unknown): Row[] => Array.isArray(value) ? value.filter(item => item && typeof item === 'object') : [];
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const probability = (value: unknown) => finite(value) && value >= 0 && value <= 1 ? `${Math.round(value * 100)}%` : 'Нет оценки';
const number = (value: unknown) => finite(value) ? value.toLocaleString('ru-RU', {maximumFractionDigits: 2}) : 'Не передано';
const time = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? date(value) : 'Время не передано';
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось получить данные';

function Source({p}: {p: Row}) {
  const name = p.model_kind === 'rules' ? 'Правила' : p.model_kind === 'stub' ? 'STUB · фиктивный ответ' : p.model_kind === 'ml' ? 'ML-модель' : 'Источник не указан';
  return <span>{name}{p.model_id ? ` · ${p.model_id}` : ''}{p.model_version ? ` · v${p.model_version}` : ''}</span>;
}

/** A new prediction creates an isolated form and async-request lifetime. */
export function PredictionDetails(props: Props) {
  return <PredictionDetailsContent key={`${props.p.id}:${props.p.object_id}`} {...props}/>;
}

function PredictionDetailsContent({p, objectName, onClose, settings, act, canDecide, canSimulate}: Props) {
  useModalFocus(true, '.prediction-details');
  const [context, setContext] = useState<Row | null>(null);
  const [analogs, setAnalogs] = useState<Row[]>([]);
  const [contextState, setContextState] = useState<LoadState>('loading');
  const [analogState, setAnalogState] = useState<LoadState>('loading');
  const [contextError, setContextError] = useState('');
  const [analogError, setAnalogError] = useState('');
  const [reload, setReload] = useState(0);
  const [delta, setDelta] = useState('10');
  const [whatIf, setWhatIf] = useState<Row | null>(null);
  const [simulationError, setSimulationError] = useState('');
  const [simulating, setSimulating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [savedDecision, setSavedDecision] = useState<Row | null>(null);
  const alive = useRef(true);
  const saveLock = useRef(false);
  const simulationLock = useRef(false);
  const decisionSection = useRef<HTMLFormElement>(null);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {if (event.key === 'Escape') {event.stopPropagation(); onClose();}};
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [onClose]);
  useEffect(() => {
    let current = true;
    setContext(null); setAnalogs([]); setContextState('loading'); setAnalogState('loading'); setContextError(''); setAnalogError('');
    void api('/objects/' + p.object_id).then(result => {if (current) {setContext(result?.context ?? null); setContextState('ready');}}).catch(error => {if (current) {setContextError(message(error)); setContextState('error');}});
    void api('/predictions/' + p.id + '/analogs').then(result => {if (current) {setAnalogs(list(result?.items)); setAnalogState('ready');}}).catch(error => {if (current) {setAnalogError(message(error)); setAnalogState('error');}});
    return () => {current = false;};
  }, [p.id, p.object_id, reload]);

  const channels = list(context?.channels);
  const temperature = channels.find(channel => channel.type_code === 'temperature');
  const points = (Array.isArray(temperature?.series?.points) ? temperature.series.points : []).filter((point: unknown) => Array.isArray(point) && typeof point[0] === 'string' && Number.isFinite(Date.parse(point[0])) && finite(point[1])).map((point: [string, number]) => ({time: time(point[0]), value: point[1]}));
  const factors = list(p.explanation?.top_factors);
  const works = list(context?.planned_works);
  const weatherForecast = list(context?.weather?.forecast);
  const weatherObserved = list(context?.weather?.observed);
  const decision = savedDecision ?? p.decision ?? list(p.decisions).slice(-1)[0];
  const reasons = settings?.reasons?.reasons && typeof settings.reasons.reasons === 'object' ? Object.entries(settings.reasons.reasons) : [];
  const editable = canDecide && p.role !== 'shadow';
  const simulatedFlood = list(whatIf?.predictions).find(row => row.incident_type === 'flood' && row.object_id === p.object_id);

  async function simulate() {
    if (!canSimulate || p.incident_type !== 'flood' || simulationLock.current) return;
    const amount = Number(delta);
    if (!delta.trim() || !Number.isFinite(amount) || amount < 0) {setSimulationError('Укажите неотрицательное число миллиметров.'); return;}
    simulationLock.current = true; setSimulating(true); setSimulationError(''); setWhatIf(null);
    try {const result = await api('/predictions/what-if', {object_ids: [p.object_id], precip_mm_delta: amount}); if (alive.current) setWhatIf(result);}
    catch (error) {if (alive.current) setSimulationError(message(error));}
    finally {simulationLock.current = false; if (alive.current) setSimulating(false);}
  }

  async function save(form: HTMLFormElement) {
    if (!editable || saveLock.current) return;
    const data = Object.fromEntries(new FormData(form));
    saveLock.current = true; setSaving(true); setSaveError('');
    try {
      await act(async () => {
        try {const result = await api('/predictions/' + p.id + '/decision', data); if (alive.current) setSavedDecision(result); return result;}
        catch (error) {if (alive.current) setSaveError(message(error)); throw error;}
      }, 'Решение сохранено в журнале');
    } catch (error) {if (alive.current) setSaveError(message(error));}
    finally {saveLock.current = false; if (alive.current) setSaving(false);}
  }

  function contextStatus() {
    if (contextState === 'loading') return <p className="pd-status" role="status">Загружаем сведения об объекте…</p>;
    if (contextState === 'error') return <p className="pd-status">Сведения не загружены. Повторите запрос выше.</p>;
    return null;
  }

  return <div className="overlay prediction-details-overlay" onClick={onClose}>
    <section role="dialog" aria-modal="true" aria-labelledby="prediction-details-title" className="drawer prediction-details" onClick={event => event.stopPropagation()}>
      <header className="pd-heading"><div><span className="pd-eyebrow">Карточка прогноза · {isDemoMode ? 'Демо' : 'Проверка человеком'}</span><h2 id="prediction-details-title">{objectName(p.object_id)}</h2><p><Source p={p}/></p></div><button type="button" onClick={onClose} aria-label="Закрыть прогноз"><X size={22}/></button></header>
      {editable && <div className="pd-shortcut"><button type="button" onClick={() => {decisionSection.current?.scrollIntoView({block: 'start'}); decisionSection.current?.focus({preventScroll: true});}}>Перейти к решению<ArrowRight size={16}/></button></div>}
      <div className="pd-body">
        <section className="pd-summary"><span className="pd-eyebrow">{incidentNames[p.incident_type] ?? 'Тип прогноза не передан'}</span><div className="pd-metrics"><div><span>Вероятность</span><strong>{probability(p.probability)}</strong></div><div><span>Горизонт</span><strong>{finite(p.horizon_h) ? `${p.horizon_h} ч` : 'Не передан'}</strong></div></div><div className="pd-summary-foot"><span className={'pd-risk pd-risk-' + p.risk}>{riskNames[p.risk] ?? 'Риск не указан'}</span><span>{time(p.as_of)}</span></div><p className="pd-caption">Прогноз не подтверждает возникновение инцидента.</p>{p.incident_type === 'intrusion_false_alarm' && <p className="pd-warning">Вероятность относится к ложности сработки, а не к риску проникновения.</p>}</section>
        {decision && <section className="pd-section pd-saved" role="status"><h3>Решение сохранено</h3><p>{outcomes[decision.outcome] ?? 'Результат не указан'}{decision.username ? ` · ${decision.username}` : ''}</p>{decision.comment && <p>{decision.comment}</p>}<small>{time(decision.ts)}</small></section>}
        <section className="pd-section"><h3>Факторы прогноза</h3>{factors.length ? factors.map((factor, index) => <div className="pd-factor" key={String(factor.feature ?? index)}><span>{factor.feature ?? 'Фактор без названия'}<small>Значение: {number(factor.value)}</small></span><strong>{finite(factor.contribution) ? `${factor.contribution > 0 ? '+' : ''}${number(factor.contribution)}` : 'Вклад не передан'}</strong></div>) : <p className="pd-status">Объяснение не передано.</p>}</section>
        {contextState === 'error' && <div className="pd-load-error" role="alert"><p>Не удалось загрузить сведения об объекте: {contextError}</p><button type="button" onClick={() => setReload(value => value + 1)}><RefreshCw size={15}/> Повторить загрузку</button></div>}
        <section className="pd-section"><h3>Температура, °C</h3>{contextStatus() ?? (points.length ? <div className="pd-chart"><DeferredChart kind="temperature" points={points}/></div> : <p className="pd-status">Ряд температуры не передан.</p>)}</section>
        <section className="pd-section"><h3>Состояние датчиков</h3>{contextStatus() ?? (channels.length ? channels.map((channel, index) => <div className="pd-channel" key={channel.channel_id ?? index}><span>{channelNames[channel.type_code] ?? channel.type_code ?? 'Тип не передан'}<small>{channel.channel_id != null ? `Канал ${channel.channel_id}` : 'Канал не передан'}</small></span><strong>{channel.health?.status === 'ok' ? 'Норма' : Array.isArray(channel.health?.reasons) && channel.health.reasons.length ? channel.health.reasons.join(', ') : channel.health?.status ? `Статус: ${channel.health.status}` : 'Не передано'}</strong></div>) : <p className="pd-status">Сведения о датчиках не переданы.</p>)}</section>
        <section className="pd-section"><h3>Плановые работы</h3>{contextStatus() ?? (works.length ? works.map((work, index) => <div className="pd-record" key={work.id ?? work.order_id ?? index}><p>{time(work.from)} — {time(work.to)}</p><small>{work.status ?? 'Статус не передан'}</small></div>) : <p className="pd-status">Не переданы. Отсутствие записей не подтверждает отсутствие работ.</p>)}</section>
        <section className="pd-section"><h3>Метеоданные</h3>{contextStatus() ?? (weatherForecast.length || weatherObserved.length ? <p>Передано наблюдений: {weatherObserved.length}; прогнозных записей: {weatherForecast.length}. Источник и полнота требуют проверки.</p> : <p className="pd-status">Не переданы. Погодные условия по этим данным неизвестны.</p>)}</section>
        <section className="pd-section"><h3>Исторические аналоги</h3>{analogState === 'loading' ? <p className="pd-status" role="status">Загружаем аналоги…</p> : analogState === 'error' ? <div className="pd-load-error" role="alert"><p>{analogError}</p><button type="button" onClick={() => setReload(value => value + 1)}><RefreshCw size={15}/> Повторить загрузку</button></div> : analogs.length ? analogs.map((analog, index) => <div className="pd-record" key={analog.id ?? index}><p>{objectName(analog.object_id)}</p><small>{time(analog.ts)}</small></div>) : <p className="pd-status">{isDemoMode ? 'Исторические аналоги в демо не загружены.' : 'В ответе сервиса подходящие случаи не найдены.'}</p>}</section>
        {p.incident_type === 'flood' && canSimulate && <section className="pd-section pd-simulation"><h3>{isDemoMode ? 'Демонстрационный сценарий осадков' : 'Сценарная оценка осадков'}</h3><p>Изменение входного параметра для сравнения расчётов. Не команда оборудованию и не прогноз погоды.</p><form onSubmit={event => {event.preventDefault(); void simulate();}}><label>Дополнительные осадки, мм<input type="number" min="0" step="any" value={delta} disabled={simulating} onChange={event => {setDelta(event.target.value); setWhatIf(null);}} required/></label><button type="submit" disabled={simulating}>{simulating ? 'Расчёт…' : 'Рассчитать сценарий'}<ArrowRight size={16}/></button></form>{simulationError && <p role="alert" className="pd-warning">{simulationError}</p>}{whatIf && <p role="status">{isDemoMode ? 'Демо-оценка' : 'Сценарная оценка'} подтопления: <strong>{probability(simulatedFlood?.probability)}</strong></p>}</section>}
        {editable ? <form ref={decisionSection} tabIndex={-1} aria-label="Решение диспетчера" className="pd-section pd-decision" onSubmit={event => {event.preventDefault(); void save(event.currentTarget);}}><h3>Решение диспетчера</h3><p>Зафиксируйте результат проверки и основание.</p><fieldset disabled={saving}><label>Действие<select name="action"><option value="inspect">Направление бригады на проверку</option><option value="dispatch">Выезд бригады</option><option value="monitor">Мониторинг ситуации</option><option value="false_alarm">Ложное срабатывание</option></select></label><label>Причина<select name="reason" required><option value="">Выберите причину</option>{reasons.map(([value, label]) => <option key={value} value={value}>{String(label)}</option>)}</select></label>{!reasons.length && <p className="pd-warning">Справочник причин не загружен. Сохранение недоступно.</p>}<label>Результат<select name="outcome"><option value="monitoring">Мониторинг</option><option value="confirmed">Подтвердился</option><option value="false">Ложный</option></select></label><label>Комментарий<textarea name="comment" minLength={3} required placeholder="Основание принятого решения"/></label></fieldset>{saveError && <p role="alert" className="pd-warning">{saveError}</p>}<button type="submit" className="pd-save" disabled={saving || !reasons.length}>{saving ? 'Сохраняем…' : 'Сохранить решение'}<ArrowRight size={18}/></button><small>Команды оборудованию и внешним системам не отправляются.</small></form> : <section className="pd-section"><p className="pd-status">{p.role === 'shadow' ? 'Теневой прогноз: запись решения недоступна.' : 'Режим просмотра. Запись решения недоступна вашей роли.'}</p></section>}
      </div>
    </section>
  </div>;
}
