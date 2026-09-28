import React, {useCallback, useState} from 'react';
import ReactDOM from 'react-dom/client';
import MapView from './MapView';
import {Row, incidentNames, riskNames} from './api';
import './style.css';
import './map-preview.css';
import {Dashboard} from './Dashboard';
import './workplace.css';
import './control-room.css';
import './reference-direction.css';
import './approved-shell.css';
import './role-approved.css';
import './approved-dispatch.css';

const positions = [[55.752,37.604],[55.764,37.584],[55.777,37.675],[55.762,37.697],[55.726,37.687],[55.725,37.555],[55.744,37.536],[55.793,37.576],[55.764,37.679],[55.715,37.662],[55.726,37.622]];
const objects = positions.map(([lat, lon], index) => ({id: `demo-${index + 1}`, name: `Коллектор ${String(index + 1).padStart(2, '0')}`, lat, lon}));
const predictions = objects.slice(0, 11).map((object, index) => ({
  id: `prediction-${index + 1}`,
  object_id: object.id,
  incident_type: index === 0 ? 'fire' : index === 1 ? 'flood' : 'sensor_failure',
  risk: index === 0 ? 'high' : index < 4 ? 'medium' : 'low',
  probability: index === 0 ? 0.86 : 0.64 - index * 0.05,
}));

function MapPreview() {
  const [selectedId, setSelectedId] = useState<string>();
  const [mobileView, setMobileView] = useState<'map' | 'signals'>('map');
  const selected = predictions.find(item => item.id === selectedId);
  const object = objects.find(item => item.id === selected?.object_id);
  const select = useCallback((prediction: Row) => setSelectedId(String(prediction.id)), []);
  return <main className="network-preview" onKeyDown={event => {if (event.key === 'Escape') setSelectedId(undefined);}}>
    <header className="network-header"><div><span className="network-brand">МОСКОЛЛЕКТОР</span><h1>Карта смены</h1></div><span className="network-demo">Демонстрационный режим</span></header>
    <nav className="network-mobile-tabs" aria-label="Рабочая область"><button aria-pressed={mobileView === 'map'} onClick={() => setMobileView('map')}>Карта</button><button aria-pressed={mobileView === 'signals'} onClick={() => setMobileView('signals')}>Сигналы · 4</button></nav>
    <div className={`network-workspace network-workspace--${mobileView}`}>
      <section className="network-map" aria-label="Карта коллекторов"><MapView objects={objects} predictions={predictions} selectedId={selectedId} onSelect={select} onFocus={select} large/></section>
      <aside className={`network-panel${selected ? ' has-selection' : ''}`} aria-label="Сигналы и выбранный участок">
        {selected && object ? <>
          <div className="network-panel-heading"><button className="network-back" onClick={() => setSelectedId(undefined)}>← К сигналам</button><button className="network-close" aria-label="Закрыть участок" onClick={() => setSelectedId(undefined)}>×</button></div>
          <span className={`network-risk network-risk--${selected.risk}`}>{riskNames[selected.risk]} риск · прогноз</span>
          <h2>{object.name}</h2><p className="network-incident">{incidentNames[selected.incident_type] ?? selected.incident_type}</p>
          <dl className="network-facts"><div><dt>Вероятность</dt><dd>{Math.round(selected.probability * 100)}%</dd></div><div><dt>Источник</dt><dd>Демосценарий</dd></div><div><dt>Телеметрия</dt><dd>Не подключена</dd></div><div><dt>Положение</dt><dd>Условное</dd></div></dl>
          <div className="network-next"><h3>Проверка сигнала</h3><p>Выберите камеру на карте для просмотра схемы ракурса. Реального видеопотока и подтверждения аварии в макете нет.</p></div>
          {selected.risk === 'high' && <a className="network-alert-link" href="/alert-preview.html">Показать сценарий красного сигнала ↗</a>}
        </> : <>
          <div className="network-panel-heading"><h2>Требуют внимания</h2><span>04</span></div>
          <p className="network-panel-description">Прогнозы риска. Выберите участок, чтобы проверить сигнал.</p>
          <div className="network-signals">{predictions.slice(0,4).map((item,index) => <button key={item.id} className="network-signal" onClick={() => select(item)}><span className={`network-risk network-risk--${item.risk}`}>{riskNames[item.risk]} риск</span><strong>{objects[index].name}</strong><span>{incidentNames[item.incident_type] ?? item.incident_type}</span><small>Демопрогноз · {Math.round(item.probability * 100)}%</small></button>)}</div>
          <div className="network-next"><h3>Камеры на схеме</h3><p>18 точек наблюдения. Нажмите квадратный маркер, чтобы открыть камеру и соседние точки ветви.</p></div>
        </>}
      </aside>
    </div>
    <footer className="network-footer">География Москвы: OpenFreeMap / OpenStreetMap. Подземная сеть, камеры и прогнозы условные.</footer>
  </main>;
}
function DispatchPreview() {
  const [message, setMessage] = useState('');
  return <div className="shell shell--control-room"><main style={{paddingTop:0}}><div className="content">
    <Dashboard objects={objects} predictions={predictions.map(p => ({...p,horizon_h:24,model_kind:'stub'}))} events={[]} recommendations={[]} objectName={id => objects.find(o => o.id === id)?.name ?? id} onSelect={p => setMessage(`Выбрано: ${objects.find(o => o.id === p.object_id)?.name}. Показания и запись решения доступны после входа в основной стенд.`)} onTab={() => setMessage('Раздел доступен после входа в основной стенд.')} onDemo={() => {}} canDecide={false} busy={false}/>
    {message && <p role="status" style={{color:'#d5e4ef'}}>{message}</p>}
  </div></main></div>;
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{new URLSearchParams(window.location.search).get('workspace') === 'dispatcher' ? <DispatchPreview/> : <MapPreview/>}</React.StrictMode>);
