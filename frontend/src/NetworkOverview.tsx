import {lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {ArrowLeft, ArrowUpRight} from 'lucide-react';
import {Row, date, incidentNames, riskNames} from './api';
import './network-overview.css';

const MapView=lazy(()=>import('./MapView'));
type Props={objects:Row[];predictions:Row[];recommendations:Row[];onSelect:(prediction:Row)=>void;onWorkSelect:(id:string)=>void};
type Filter='all'|'attention'|'work';
const statusNames:Record<string,string>={new:'Новая',accepted:'Принята',completed:'Выполнена',rejected:'Отклонена'};
const summaryNames:Record<string,string>={new:'новых',accepted:'принято',completed:'выполнено',rejected:'отклонено'};
const severity:Record<string,number>={high:4,medium:3,low:2,normal:1,insufficient:0};
const probability=(p:Row)=>typeof p.probability==='number'&&Number.isFinite(p.probability)?p.probability:-1;
const compareRisk=(a:Row,b:Row)=>(severity[b.risk]??-1)-(severity[a.risk]??-1)||probability(b)-probability(a);
const source=(p:Row)=>p.model_kind==='rules'?'Правила':p.model_kind==='stub'?'STUB · демонстрация':p.model_id?`${p.model_id}${p.model_version?' / '+p.model_version:''}`:'Источник не указан';

export function NetworkOverview({objects,predictions,recommendations,onSelect,onWorkSelect}:Props){
  const [query,setQuery]=useState(''),[filter,setFilter]=useState<Filter>('all'),[selectedObjectId,setSelectedObjectId]=useState<string|null>(null);
  const detailHeading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{if(selectedObjectId&&window.matchMedia('(max-width:900px)').matches){detailHeading.current?.focus({preventScroll:true});detailHeading.current?.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}},[selectedObjectId]);
  const forecasts=useMemo(()=>{
    const byObject=new Map<string,Row[]>();
    for(const prediction of predictions){
      if(prediction.incident_type==='intrusion_false_alarm')continue;
      const key=String(prediction.object_id);
      byObject.set(key,[...(byObject.get(key)??[]),prediction]);
    }
    for(const group of byObject.values())group.sort(compareRisk);
    return byObject;
  },[predictions]);
  const workByObject=useMemo(()=>{
    const result=new Map<string,Row[]>();
    for(const work of recommendations){const key=String(work.object_id);result.set(key,[...(result.get(key)??[]),work])}
    return result;
  },[recommendations]);
  const counts=useMemo(()=>Object.fromEntries(Object.keys(statusNames).map(status=>[status,recommendations.filter(work=>work.data?.status===status).length])),[recommendations]);
  const visible=useMemo(()=>objects.filter(object=>{
    if(!String(object.name??object.id).toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')))return false;
    if(filter==='attention')return (forecasts.get(String(object.id))??[]).some(p=>['high','medium'].includes(p.risk)&&!p.decision);
    if(filter==='work')return (workByObject.get(String(object.id))??[]).some(work=>['new','accepted'].includes(work.data?.status));
    return true;
  }),[objects,query,filter,forecasts,workByObject]);
  const mapPredictions=useMemo(()=>visible.flatMap(object=>{const p=forecasts.get(String(object.id))?.[0];return p?[p]:[]}),[visible,forecasts]);
  const selected=objects.find(object=>String(object.id)===selectedObjectId);
  const selectedPredictions=selected?forecasts.get(String(selected.id))??[]:[];
  const highest=selectedPredictions[0];
  const selectedWorks=selected?workByObject.get(String(selected.id))??[]:[];
  const selectMapObject=useCallback((prediction:Row)=>setSelectedObjectId(String(prediction.object_id)),[]);
  const selectObject=useCallback((object:Row)=>setSelectedObjectId(String(object.id)),[]);
  return <section className="network-overview" aria-labelledby="network-overview-title">
    <header><div><h2 id="network-overview-title">Участки и работы</h2><p>По загруженным записям; назначение бригад не передано</p></div></header>
    <div className="network-summary" aria-label="Состояние рекомендаций">{Object.entries(summaryNames).map(([key,name])=><span key={key}><b>{counts[key]}</b>{name}</span>)}</div>
    <div className="network-body"><div className="network-map" aria-label="Карта участков"><Suspense fallback={<p role="status">Загрузка карты…</p>}><MapView large objects={visible} predictions={mapPredictions} selectedId={highest?.id} focusedObjectId={selectedObjectId??undefined} onObjectSelect={selectObject} onSelect={selectMapObject} onFocus={selectMapObject}/></Suspense></div>
      <aside className="network-panel" aria-label={selected?'Выбранный участок':'Список участков'}>
        {!selected&&<div className="network-toolbar"><label>Поиск участка<input type="search" aria-label="Поиск участка по названию" placeholder="Название участка…" value={query} onChange={event=>{setQuery(event.target.value);setSelectedObjectId(null)}}/></label><label>Показать<select value={filter} onChange={event=>{setFilter(event.target.value as Filter);setSelectedObjectId(null)}}><option value="all">Все участки</option><option value="attention">Требуют внимания</option><option value="work">Есть работы</option></select></label></div>}
        {selected?<div className="network-detail"><button type="button" onClick={()=>setSelectedObjectId(null)}><ArrowLeft size={16}/>Весь список</button><h3 ref={detailHeading} tabIndex={-1}>{selected.name??selected.id}</h3>
          {highest?<><span className={`badge ${highest.risk}`}>{riskNames[highest.risk]??'Уровень не указан'} · прогноз</span><p>{incidentNames[highest.incident_type]??'Тип прогноза не указан'}</p><dl><div><dt>Вероятность</dt><dd>{probability(highest)<0?'Нет оценки':`${Math.round(highest.probability*100)}%`}</dd></div><div><dt>Источник</dt><dd>{source(highest)}</dd></div><div><dt>Горизонт</dt><dd>{typeof highest.horizon_h==='number'?`${highest.horizon_h} ч`:'Не передан'}</dd></div><div><dt>Срез</dt><dd>{highest.as_of?date(highest.as_of):'Не передан'}</dd></div><div><dt>Решение</dt><dd>{highest.decision?({confirmed:'Подтвердился',false:'Ложный',monitoring:'Мониторинг'} as Record<string,string>)[highest.decision.outcome]??'Записано':'Ещё не принято'}</dd></div></dl><button type="button" className="primary network-open" onClick={()=>onSelect(highest)}>Открыть прогноз<ArrowUpRight size={16}/></button>{selectedPredictions.length>1&&<p>Оперативных прогнозов: {selectedPredictions.length}. Показан наиболее высокий риск.</p>}</>:<p className="network-empty">Нет оперативного прогноза. Состояние участка по этим данным определить нельзя.</p>}
          <h4>Связанные работы · {selectedWorks.length}</h4>{selectedWorks.length?selectedWorks.map(work=><button type="button" className="network-object network-work" key={work.id} onClick={()=>onWorkSelect(String(work.id))}><span><strong>{work.data?.action??'Действие не указано'}</strong><small>{statusNames[work.data?.status]??'Статус не указан'}</small></span><ArrowUpRight size={16}/></button>):<p>В загруженных записях нет связанных работ.</p>}
        </div>:<><div className="network-panel-heading"><h3>Участки</h3><span>{visible.length} из {objects.length}</span></div>{visible.length?visible.map(object=>{const p=forecasts.get(String(object.id))?.[0],works=workByObject.get(String(object.id))??[];return <button type="button" className="network-object" key={object.id} onClick={()=>setSelectedObjectId(String(object.id))}><span><strong>{object.name??object.id}</strong><small>{p?`${riskNames[p.risk]??'Уровень не указан'} риск · прогноз`:'Нет оперативного прогноза'}</small><small>Открытых работ: {works.filter(work=>['new','accepted'].includes(work.data?.status)).length}</small></span><ArrowUpRight size={16}/></button>}):<p className="network-empty">{objects.length?'Поиск и фильтры не дали результатов.':'Объекты не загружены.'}</p>}</>}
      </aside>
    </div>
  </section>;
}
