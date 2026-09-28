import {useEffect, useMemo, useRef} from 'react';
import {Row, incidentNames, riskNames} from './api';
import './tunnel-scene.css';

type Props = {
  objects: Row[];
  predictions: Row[];
  selectedId?: string;
  onFocus: (prediction: Row) => void;
};

const MAX_NODES = 13;
const DEMO_POSITIONS = [
  [50, 50], [24, 27], [39, 17], [57, 18],
  [75, 25], [82, 39], [80, 59], [75, 75],
  [60, 82], [42, 81], [25, 74], [19, 58], [18, 43],
] as const;

type SceneNode = {object: Row; prediction?: Row};

function score(prediction?: Row) {
  if (prediction?.probability == null) return -1;
  const value = Number(prediction?.probability);
  return Number.isFinite(value) ? value : -1;
}

function riskClass(risk: unknown) {
  return risk === 'high' || risk === 'medium' || risk === 'low' || risk === 'normal'
    ? risk
    : 'unknown';
}

export default function TunnelScene({objects, predictions, selectedId, onFocus}: Props) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const {nodes, total} = useMemo(() => {
    const byObject = new Map<string, Row>();
    for (const prediction of predictions) {
      if (prediction.object_id == null) continue;
      const key = String(prediction.object_id);
      const current = byObject.get(key);
      if (!current || score(prediction) > score(current)) byObject.set(key, prediction);
    }

    const selected = predictions.find(prediction => String(prediction.id) === selectedId);
    if (selected?.object_id != null) byObject.set(String(selected.object_id), selected);

    const all: SceneNode[] = objects.map(object => ({
      object,
      prediction: byObject.get(String(object.id)),
    }));
    const selectedIndex = selectedId == null ? -1 : all.findIndex(node => String(node.prediction?.id) === selectedId);
    const visible = all.slice(0, MAX_NODES);
    if (selectedIndex >= MAX_NODES) visible[MAX_NODES - 1] = all[selectedIndex];
    return {nodes: visible, total: all.length};
  }, [objects, predictions, selectedId]);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas && window.matchMedia('(max-width: 540px)').matches) {
      canvas.scrollLeft = Math.max(0, (canvas.scrollWidth - canvas.clientWidth) / 2);
    }
  }, [selectedId, nodes.length]);
  const selectedNode = selectedId ? nodes.find(node => String(node.prediction?.id) === selectedId) : undefined;

  return <section className="tunnel-scene" aria-label="Демонстрационная схема объектов коллекторов">
    <header className="tunnel-scene__head">
      <div>
        <span className="tunnel-scene__eyebrow">КОНТУР / УСЛОВНАЯ СХЕМА</span>
        <h3>Сеть коллекторов Москвы</h3>
      </div>
      <span className="tunnel-scene__count">{nodes.length} / {total} объектов</span>
    </header>

    <div className="tunnel-scene__notice" role="note">
      Условная схема для демо. Линии не отражают реальные трассы; точные координаты и камеры не подключены.
    </div>

    <div className="tunnel-scene__canvas" ref={canvasRef}>
      <div className="tunnel-scene__plan">
        <div className="tunnel-scene__map-underlay" aria-hidden="true"/>
        <svg className="tunnel-scene__routes" viewBox="0 0 1000 500" preserveAspectRatio="none" aria-hidden="true">
          <path className="tunnel-scene__route-edge tunnel-scene__route-edge--main" d="M500 250 C430 226 344 178 240 135 M500 250 C578 219 657 160 750 125 M500 250 C578 276 671 327 750 375 M500 250 C424 282 329 342 250 370"/>
          <path className="tunnel-scene__route-floor tunnel-scene__route-floor--main" d="M500 250 C430 226 344 178 240 135 M500 250 C578 219 657 160 750 125 M500 250 C578 276 671 327 750 375 M500 250 C424 282 329 342 250 370"/>
          <path className="tunnel-scene__route-edge tunnel-scene__route-edge--branch" d="M343 180 C354 141 373 111 390 85 M619 193 C601 152 585 120 570 90 M675 159 C735 161 786 174 820 195 M655 310 C718 306 770 301 800 295 M674 328 C658 360 626 391 600 410 M364 323 C376 361 398 387 420 405 M294 348 C251 320 218 301 190 290 M347 183 C282 187 226 200 180 215 M425 216 C434 194 466 183 500 184 C543 185 568 202 584 224 M585 278 C558 301 527 315 493 312 C459 310 428 296 411 276"/>
          <path className="tunnel-scene__route-floor tunnel-scene__route-floor--branch" d="M343 180 C354 141 373 111 390 85 M619 193 C601 152 585 120 570 90 M675 159 C735 161 786 174 820 195 M655 310 C718 306 770 301 800 295 M674 328 C658 360 626 391 600 410 M364 323 C376 361 398 387 420 405 M294 348 C251 320 218 301 190 290 M347 183 C282 187 226 200 180 215 M425 216 C434 194 466 183 500 184 C543 185 568 202 584 224 M585 278 C558 301 527 315 493 312 C459 310 428 296 411 276"/>
          <path className="tunnel-scene__route-brace" d="M305 158 L300 172 M402 209 L397 224 M590 204 L598 218 M697 146 L702 160 M601 280 L592 293 M691 345 L684 358 M400 304 L410 317 M304 340 L314 352"/>
          <circle className="tunnel-scene__junction" cx="500" cy="250" r="10"/>
        </svg>
        <div className="tunnel-scene__map-label" aria-hidden="true">СХЕМА / БЕЗ ГЕОПРИВЯЗКИ</div>
        {selectedNode?.prediction && <button type="button" className="tunnel-scene__focus-readout" onClick={() => onFocus(selectedNode.prediction!)}>
          <span>ВЫБРАННЫЙ ПРОГНОЗ</span>
          <strong>{String(selectedNode.object.name)}</strong>
          <small>{incidentNames[selectedNode.prediction.incident_type] ?? 'Прогноз'}</small>
        </button>}
      {nodes.length ? <div className="tunnel-scene__nodes">
        {nodes.map(({object, prediction}, index) => {
          const [x, y] = DEMO_POSITIONS[index];
          const selected = prediction != null && String(prediction.id) === selectedId;
          const risk = riskClass(prediction?.risk);
          const riskLabel = prediction ? (riskNames[prediction.risk] ?? 'Риск не указан') : 'Нет прогноза';
          const probability = score(prediction);
          const label = String(object.name || object.tag || object.id);
          const compactLabel = label.replace(/^Коллектор\s+/i, 'К-');
          const compactRisk = risk === 'unknown' ? 'НЕТ ДАННЫХ' : probability >= 0 ? `${risk === 'high' ? 'РИСК' : riskNames[prediction?.risk] ?? 'ОЦЕНКА'} ${Math.round(probability * 100)}%` : riskLabel;
          const content = <>
            <span className="tunnel-scene__slot" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
            <span className="tunnel-scene__node-copy">
              <strong title={label}>{compactLabel}</strong>
              <small>{prediction ? (incidentNames[prediction.incident_type] ?? 'Прогноз') : 'Нет прогноза'}</small>
            </span>
            <span className="tunnel-scene__risk">
              <span className="tunnel-scene__signal" aria-hidden="true"/>
              <span>{compactRisk}</span>
            </span>
          </>;
          return prediction
            ? <button
                type="button"
                key={String(object.id)}
                className={`tunnel-scene__node tunnel-scene__node--${risk}${index === 0 ? ' is-focus' : ''}${selected ? ' is-selected' : ''}`}
                style={{left: `${x}%`, top: `${y}%`}}
                aria-label={`${label}. ${riskLabel}${probability >= 0 ? `, ${Math.round(probability * 100)} процентов` : ''}. Открыть прогноз`}
                title={`${label} · ${riskLabel}`}
                aria-pressed={selected}
                onClick={() => onFocus(prediction)}
              >{content}</button>
            : <div key={String(object.id)} className={`tunnel-scene__node tunnel-scene__node--unknown${index === 0 ? ' is-focus' : ''}`} style={{left: `${x}%`, top: `${y}%`}} aria-label={`${label}. Нет прогноза`}>{content}</div>;
        })}
      </div> : <div className="tunnel-scene__empty">Объекты для схемы не загружены.</div>}
      </div>
    </div>

    <footer className="tunnel-scene__foot">
      <span>Положение узлов и соединения условные, без привязки к местности.</span>
      {total > nodes.length && <span>Показаны {nodes.length} объектов: по оценке риска и выбранный.</span>}
    </footer>
  </section>;
}
