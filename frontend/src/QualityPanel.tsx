import {useCallback, useEffect, useRef, useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {api, date, isDemoMode, Row} from './api';
import './quality-panel.css';

type Props={act:(task:()=>Promise<unknown>,message?:string,refresh?:boolean)=>Promise<void>;role:string;objects:Row[]};
const metricDefinitions=[
  {key:'precision',name:'Точность предупреждений',code:'Precision',description:'Доля подтверждённых случаев среди положительных прогнозов.'},
  {key:'recall',name:'Полнота обнаружения',code:'Recall',description:'Доля найденных системой случаев среди фактически произошедших.'},
  {key:'f1',name:'Баланс точности и полноты',code:'F1',description:'Гармоническое среднее Precision и Recall. Чем ближе к 1, тем лучше.'},
  {key:'brier',name:'Ошибка вероятностей',code:'Brier score',description:'Средняя квадратичная ошибка вероятности. Чем ближе к 0, тем лучше.'},
];
const number=(value:unknown,digits=3)=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('ru-RU',{maximumFractionDigits:digits,minimumFractionDigits:digits}):'Нет оценки';
const errorText=(cause:unknown)=>cause instanceof Error?cause.message:'Не удалось получить данные';
const today=new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'});
const weekAgo=new Date(Date.now()-7*86400000).toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'});

export function QualityPanel({act,role,objects}:Props){
  const [metrics,setMetrics]=useState<Row|null>(null),[comparison,setComparison]=useState<Row[]|null>(null);
  const [loading,setLoading]=useState(true),[metricsError,setMetricsError]=useState(''),[comparisonError,setComparisonError]=useState('');
  const [start,setStart]=useState(weekAgo),[end,setEnd]=useState(today),[objectId,setObjectId]=useState('');
  const [running,setRunning]=useState(false),[formError,setFormError]=useState(''),[resultMessage,setResultMessage]=useState('');
  const request=useRef(0);
  const canBacktest=!isDemoMode&&['analyst','admin'].includes(role);
  const load=useCallback(async()=>{
    const current=++request.current;
    setLoading(true);setMetricsError('');setComparisonError('');
    const [m,c]=await Promise.allSettled([api('/evaluation/metrics'),api('/evaluation/model-comparison')]);
    if(current!==request.current)return;
    if(m.status==='fulfilled'){setMetrics(m.value)}else{setMetrics(null);setMetricsError(errorText(m.reason))}
    if(c.status==='fulfilled'&&Array.isArray(c.value)){setComparison(c.value)}else{setComparison(null);setComparisonError(c.status==='rejected'?errorText(c.reason):'Сервис вернул неизвестный формат сравнения')}
    setLoading(false);
  },[]);
  useEffect(()=>{void load();return()=>{request.current++}},[load]);
  async function runBacktest(){
    setFormError('');setResultMessage('');
    if(!canBacktest)return;
    const from=new Date(`${start}T00:00:00+03:00`),to=new Date(`${end}T00:00:00+03:00`);
    if(!Number.isFinite(from.getTime())||!Number.isFinite(to.getTime())||to<=from){setFormError('Дата окончания должна быть позже даты начала.');return}
    const objectIds=objectId?objects.filter(object=>String(object.id)===objectId).map(object=>String(object.id)):objects.map(object=>String(object.id));
    if(!objectIds.length){setFormError('Нет доступных объектов для расчёта. Обновите данные рабочего места.');return}
    setRunning(true);
    try {
      await act(async()=>{
        try {
          const result=await api('/evaluation/backtest',{start:from.toISOString(),end:to.toISOString(),step_hours:24,object_ids:objectIds});
          setResultMessage(typeof result.predictions==='number'?`Расчёт завершён. Обработано прогнозов: ${result.predictions}.`:'Расчёт завершён. Результаты обновлены.');
          await load();
        } catch(cause){setFormError(errorText(cause))}
      },'',false);
    } finally {setRunning(false)}
  }
  const count=typeof metrics?.count==='number'?metrics.count:0;
  const points=Array.isArray(metrics?.series)?metrics.series.slice(-100):[];
  return <section className="panel quality-panel" aria-labelledby="quality-panel-title">
    <header className="quality-heading"><div><span className="quality-kicker">АНАЛИТИКА / ОЦЕНКА ПРОГНОЗОВ</span><h2 id="quality-panel-title">Качество сохранённых прогнозов</h2><p>Только завершённые горизонты с известным покрытием наблюдений. Метрики синтетики не подтверждают точность на реальных объектах.</p></div><button type="button" disabled={loading||running} onClick={()=>void load()}><RefreshCw size={16}/>{loading?'Загрузка…':'Обновить'}</button></header>
    <section className="quality-section" aria-label="Метрики качества" aria-busy={loading}>
      {loading?<p className="quality-state" role="status">Загружаем оценку прогнозов…</p>:metricsError?<div className="quality-state quality-error" role="alert"><p>Не удалось загрузить метрики: {metricsError}</p><button type="button" onClick={()=>void load()}>Повторить загрузку</button></div>:count>0?<>
        <p className="quality-sample">Оценённых прогнозов: <b>{count.toLocaleString('ru-RU')}</b></p>
        <dl className="quality-metrics">{metricDefinitions.map(metric=><div key={metric.key}><dt>{metric.name}<small>{metric.code}</small></dt><dd>{number(metrics?.[metric.key])}</dd><p>{metric.description}</p></div>)}</dl>
        <dl className="quality-extra"><div><dt>Площадь под кривой точности и полноты · PR-AUC</dt><dd>{number(metrics?.pr_auc)}</dd></div><div><dt>Среднее опережение, ч</dt><dd>{number(metrics?.lead_time_h,1)}</dd></div><div><dt>Ложные тревоги на объект в сутки</dt><dd>{number(metrics?.false_alarms_per_object_day)}</dd></div></dl>
        <h3>Прогноз и наблюдаемый исход</h3><p className="quality-note">Последние {points.length} записей. Вероятность от 0 до 1; исход: 1 — случай произошёл, 0 — не произошёл.</p>
        {points.length?<div className="quality-chart" role="img" aria-label={`График вероятностей прогнозов и наблюдаемых исходов, ${points.length} записей`}><ResponsiveContainer width="100%" height={260}><LineChart data={points}><CartesianGrid stroke="#d9e3f2" strokeDasharray="3 3" vertical={false}/><XAxis dataKey="as_of" tickFormatter={date} minTickGap={65} stroke="#6c7fa3"/><YAxis domain={[0,1]} width={36} stroke="#6c7fa3"/><Tooltip labelFormatter={value=>date(String(value))}/><Line dataKey="probability" name="Вероятность прогноза" stroke="#40558f" strokeWidth={2} dot={false}/><Line dataKey="label" name="Наблюдаемый исход" stroke="#b26a38" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></div>:<p className="quality-state">Временной ряд сервисом не передан.</p>}
      </>:<div className="quality-state"><h3>Пока нет оценённых прогнозов</h3><p>{isDemoMode?'В локальном демо качество модели не имитируется.':canBacktest?'Можно запустить ретроспективный расчёт по доступным объектам.':'Результаты появятся после ретроспективного расчёта, который выполняет аналитик.'} Отсутствие оценки не означает нулевую точность.</p></div>}
    </section>
    <section className="quality-section" aria-labelledby="quality-backtest-title"><h3 id="quality-backtest-title">Ретроспективный расчёт</h3><p className="quality-note">Шаг 24 часа. Границы периода — начало выбранного дня по Москве. Все объекты означают только загруженный в рабочее место список.</p><form className="quality-backtest" onSubmit={event=>{event.preventDefault();void runBacktest()}}><label>Начало<input type="date" required value={start} disabled={!canBacktest||running} onChange={event=>setStart(event.target.value)}/></label><label>Конец<input type="date" required value={end} disabled={!canBacktest||running} onChange={event=>setEnd(event.target.value)}/></label><label>Объекты<select value={objectId} disabled={!canBacktest||running||!objects.length} onChange={event=>setObjectId(event.target.value)}><option value="">Все загруженные · {objects.length}</option>{objects.map(object=><option key={object.id} value={object.id}>{object.name??object.id}</option>)}</select></label><button type="submit" className="primary" disabled={!canBacktest||running||!objects.length}>{running?'Выполняется расчёт…':'Рассчитать'}</button></form>
      {!canBacktest&&<p className="quality-note">{isDemoMode?'В локальном демо расчёт недоступен: требуется подключённый сервис.':'Запуск доступен аналитику и администратору. Руководитель просматривает результаты.'}</p>}{canBacktest&&!objects.length&&<p className="quality-note">Объекты для расчёта не загружены.</p>}{formError&&<p role="alert" className="quality-error">{formError}</p>}{resultMessage&&<p role="status" className="quality-result">{resultMessage}</p>}
    </section>
    <section className="quality-section" aria-labelledby="quality-comparison-title" aria-busy={loading}><h3 id="quality-comparison-title">Сравнение версий и режимов</h3>{loading?<p role="status">Загружаем сравнение…</p>:comparisonError?<div role="alert" className="quality-error"><p>Не удалось загрузить сравнение: {comparisonError}</p><button type="button" onClick={()=>void load()}>Повторить загрузку</button></div>:comparison?.length?<div className="table-scroll"><table><thead><tr><th>Модель / версия</th><th>Режим</th><th>Оценено</th><th>F1</th></tr></thead><tbody>{comparison.map((row,index)=><tr key={`${row.model_id}-${row.version}-${row.role}-${index}`}><td>{row.model_id??'Не указана'} / {row.version??'—'}</td><td>{({active:'Активный',shadow:'Теневой',backtest:'Ретроспективный'} as Record<string,string>)[row.role]??row.role??'Не указан'}</td><td>{typeof row.metrics?.count==='number'?row.metrics.count:'Не передано'}</td><td>{row.metrics?.count>0?number(row.metrics?.f1):'Нет оценки'}</td></tr>)}</tbody></table></div>:<p className="quality-state">Нет данных для сравнения версий. Сервис не вернул оценённые группы.</p>}</section>
    <footer className="quality-reports">{isDemoMode?<p>Отчёты XLSX и PDF доступны на основном стенде с подключённым сервисом.</p>:<><span>Отчёт по сохранённым прогнозам</span><a href="/api/v1/reports/predictions?format=xlsx">Скачать XLSX</a><a href="/api/v1/reports/predictions?format=pdf">Скачать PDF</a></>}</footer>
  </section>;
}
