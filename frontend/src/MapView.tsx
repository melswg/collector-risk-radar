import {useEffect, useMemo, useRef, useState} from 'react';
import {Camera, Layers3, MapPin, RotateCcw, X} from 'lucide-react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import {Row, riskNames} from './api';
import {watchMapAvailability} from './map-availability';
import './underground-map.css';

type Coordinate = [number, number];
type CameraPoint = {id: string; group: string; place: string; coordinate: Coordinate};
const CENTER: Coordinate = [37.6184, 55.7512];
maplibregl.setWorkerUrl(workerUrl);
const ROUTES: {kind: 'main' | 'branch'; points: Coordinate[]}[] = [
  {kind: 'main', points: [[37.604,55.752],[37.608,55.760],[37.618,55.764],[37.629,55.760],[37.634,55.752],[37.630,55.744],[37.618,55.740],[37.606,55.744],[37.604,55.752]]},
  {kind: 'main', points: [[37.608,55.760],[37.596,55.759],[37.584,55.764],[37.574,55.768],[37.550,55.773]]},
  {kind: 'main', points: [[37.629,55.760],[37.643,55.765],[37.661,55.772],[37.675,55.777],[37.686,55.784]]},
  {kind: 'main', points: [[37.630,55.744],[37.650,55.735],[37.674,55.729],[37.687,55.726],[37.699,55.720]]},
  {kind: 'main', points: [[37.606,55.744],[37.587,55.736],[37.568,55.730],[37.555,55.725],[37.544,55.718]]},
  {kind: 'branch', points: [[37.574,55.768], [37.571,55.783], [37.576,55.793]]},
  {kind: 'branch', points: [[37.661,55.772], [37.679,55.764], [37.697,55.762]]},
  {kind: 'branch', points: [[37.674,55.729], [37.662,55.715], [37.659,55.706]]},
  {kind: 'branch', points: [[37.568,55.730], [37.549,55.739], [37.536,55.744]]},
  {kind: 'branch', points: [[37.596,55.759], [37.604,55.770], [37.620,55.773], [37.643,55.765]]},
  {kind: 'branch', points: [[37.587,55.736], [37.603,55.729], [37.622,55.726], [37.650,55.735]]},
];
const CAMERA_GROUPS: {group: string; points: Coordinate[]}[] = [
  {group: 'Северо-запад', points: [[37.596,55.759],[37.574,55.768],[37.550,55.773]]},
  {group: 'Северо-восток', points: [[37.643,55.765],[37.661,55.772],[37.686,55.784]]},
  {group: 'Юго-восток', points: [[37.650,55.735],[37.674,55.729],[37.699,55.720]]},
  {group: 'Юго-запад', points: [[37.587,55.736],[37.568,55.730],[37.544,55.718]]},
  {group: 'Северная ветвь', points: [[37.571,55.783],[37.620,55.773],[37.679,55.764]]},
  {group: 'Южная ветвь', points: [[37.549,55.739],[37.622,55.726],[37.662,55.715]]},
];
const CAMERA_PLACES = ['Входной узел', 'Основной ход', 'Ответвление'];
const CAMERAS: CameraPoint[] = CAMERA_GROUPS.flatMap((sector, groupIndex) => sector.points.map((coordinate, index) => ({
  id: `К-${String(groupIndex * 3 + index + 1).padStart(2, '0')}`,
  group: sector.group,
  place: CAMERA_PLACES[index],
  coordinate,
})));
const ROUTE_DATA = {
  type: 'FeatureCollection' as const,
  features: ROUTES.map((route, index) => ({type: 'Feature' as const, properties: {kind: route.kind, id: index}, geometry: {type: 'LineString' as const, coordinates: route.points}})),
};
const ROUTE_LAYERS = ['demo-route-main-edge','demo-route-main-core','demo-route-branch-edge','demo-route-branch-core','demo-route-selected','demo-route-hit'];

function frameNetwork(map: maplibregl.Map) {
  const bounds = new maplibregl.LngLatBounds();
  ROUTES.forEach(route => route.points.forEach(point => bounds.extend(point)));
  map.fitBounds(bounds, {padding: {top: 95, bottom: 85, left: 35, right: 35}, maxZoom: 12.3, duration: 0});
}

function styleVectorMap(map: maplibregl.Map) {
  for (const layer of map.getStyle().layers ?? []) {
    const id = layer.id.toLowerCase();
    try {
      if (layer.type === 'background') map.setPaintProperty(layer.id, 'background-color', '#edf6ff');
      if (layer.type === 'raster') map.setLayoutProperty(layer.id, 'visibility', 'none');
      if (layer.type === 'fill') map.setPaintProperty(layer.id, 'fill-color', id.includes('water') ? '#c9e5fa' : id.includes('park') || id.includes('grass') ? '#e0eee9' : '#eaf3fd');
      if (layer.type === 'line') {
        const color = id.includes('water') ? '#b7d7ee' : '#ffffff';
        map.setPaintProperty(layer.id, 'line-color', color);
        map.setPaintProperty(layer.id, 'line-opacity', id.includes('minor') || id.includes('service') ? .4 : .8);
      }
      if (layer.type === 'symbol') {
        if(id.includes('poi')||id.includes('housenumber')) map.setLayoutProperty(layer.id,'visibility','none');
        map.setPaintProperty(layer.id, 'text-color', '#7b94bd');
        map.setPaintProperty(layer.id, 'text-halo-color', '#edf6ff');
      }
    } catch { /* Some source styles use incompatible paint properties. */ }
  }
}

function addDemoRoutes(map: maplibregl.Map) {
  map.addSource('demo-collector-routes', {type: 'geojson', data: ROUTE_DATA});
  for (const kind of ['main','branch'] as const) {
    for (const part of ['edge','core'] as const) {
      map.addLayer({id: `demo-route-${kind}-${part}`, type: 'line', source: 'demo-collector-routes', filter: ['==',['get','kind'],kind], layout: {'line-cap':'round','line-join':'round'}, paint: {
        'line-color': part === 'edge' ? '#405c99' : '#c0dcf4',
        'line-width': kind === 'main' ? part === 'edge' ? 7 : 3 : part === 'edge' ? 5 : 2,
        'line-opacity': part === 'edge' ? .95 : .91,
      }});
    }
  }
  map.addLayer({id:'demo-route-selected',type:'line',source:'demo-collector-routes',filter:['==',['get','id'],-1],layout:{'line-cap':'round','line-join':'round'},paint:{'line-width':3,'line-color':'#a66432'}});
  map.addLayer({id:'demo-route-hit',type:'line',source:'demo-collector-routes',layout:{'line-cap':'round','line-join':'round'},paint:{'line-width':22,'line-color':'#ffffff','line-opacity':0}});
}

export default function MapView({objects, predictions, onSelect, onFocus, onObjectSelect, focusedObjectId, selectedId, large = false}: {objects: Row[]; predictions: Row[]; onSelect: (p: Row) => void; onFocus?: (p: Row) => void; onObjectSelect?: (object:Row)=>void; focusedObjectId?: string; selectedId?: string; large?: boolean}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const cameraMarkers = useRef<maplibregl.Marker[]>([]);
  const objectMarkers = useRef<maplibregl.Marker[]>([]);
  const selectionHandlers = useRef({onSelect, onFocus, onObjectSelect});
  useEffect(() => {selectionHandlers.current = {onSelect, onFocus, onObjectSelect};}, [onSelect, onFocus, onObjectSelect]);
  const canSelectObject = !!onObjectSelect;
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [showCameras, setShowCameras] = useState(true);
  const [showRoutes, setShowRoutes] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [mapAttempt, setMapAttempt] = useState(0);
  const selectedCamera = CAMERAS.find(camera => camera.id === selectedCameraId);
  const selectedObject = objects.find(object => String(object.id)===focusedObjectId || predictions.some(p => p.id === selectedId && p.object_id === object.id));
  const predictionsByObject = useMemo(() => {
    const grouped = new Map<string, Row>();
    for (const prediction of predictions) {
      if (prediction.incident_type === 'intrusion_false_alarm') continue;
      const key = String(prediction.object_id);
      const previous = grouped.get(key);
      if (!previous || (prediction.probability ?? 0) > (previous.probability ?? 0)) grouped.set(key, prediction);
    }
    return grouped;
  }, [predictions]);

  useEffect(() => {
    if (!containerRef.current) return;
    setMapReady(false);
    setMapError(false);
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({container: containerRef.current, style: 'https://tiles.openfreemap.org/styles/liberty', center: CENTER, zoom: 11.8, minZoom: 10, maxZoom: 17});
    } catch {
      setMapError(true);
      return;
    }
    mapRef.current = map;
    const stopWatching = watchMapAvailability(map, setMapError);
    map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'bottom-right');
    map.on('load', () => {
      styleVectorMap(map); addDemoRoutes(map); frameNetwork(map); setMapReady(true);
      map.on('mouseenter','demo-route-hit',() => {map.getCanvas().style.cursor='pointer';});
      map.on('mouseleave','demo-route-hit',() => {map.getCanvas().style.cursor='';});
      map.on('click','demo-route-hit',event => {
        const distance = (camera: CameraPoint) => ((camera.coordinate[0]-event.lngLat.lng)*Math.cos(event.lngLat.lat*Math.PI/180))**2+(camera.coordinate[1]-event.lngLat.lat)**2;
        const nearest = CAMERAS.reduce((best,camera) => distance(camera)<distance(best) ? camera : best);
        setShowCameras(true);
        setSelectedCameraId(nearest.id);
      });
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(containerRef.current);
    CAMERAS.forEach(camera => {
      const element = document.createElement('button');
      element.type = 'button';
      element.className = 'underground-camera-pin';
      element.title = `${camera.id}: ${camera.place}, условная камера`;
      element.setAttribute('aria-label', element.title);
      element.innerHTML = '<span aria-hidden="true"></span>';
      element.addEventListener('click', event => {event.stopPropagation(); setSelectedCameraId(camera.id);});
      cameraMarkers.current.push(new maplibregl.Marker({element, anchor: 'center'}).setLngLat(camera.coordinate).addTo(map));
    });
    return () => {stopWatching(); observer.disconnect(); cameraMarkers.current = []; objectMarkers.current = []; map.remove(); mapRef.current = null;};
  }, [mapAttempt]);

  useEffect(() => {
    cameraMarkers.current.forEach(marker => {marker.getElement().hidden = !showCameras;});
    if (!showCameras) setSelectedCameraId(null);
  }, [showCameras, mapAttempt]);
  useEffect(() => {
    cameraMarkers.current.forEach((marker,index) => marker.getElement().setAttribute('aria-pressed',String(CAMERAS[index].id === selectedCameraId)));
  }, [selectedCameraId, mapAttempt]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => ROUTE_LAYERS.forEach(id => {if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', showRoutes ? 'visible' : 'none');});
    update(); map.on('load', update);
    return () => {map.off('load', update);};
  }, [showRoutes, mapAttempt]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    objectMarkers.current.forEach(marker => marker.remove());
    objectMarkers.current = objects.filter(object => Number.isFinite(object.lat) && Number.isFinite(object.lon)).map(object => {
      const prediction = predictionsByObject.get(String(object.id));
      const element = document.createElement('button');
      element.type = 'button';
      element.className = `underground-object-pin ${prediction?.risk ?? 'unknown'}${String(object.id)===focusedObjectId || prediction && selectedId === prediction.id ? ' selected' : ''}`;
      element.title = `${String(object.name ?? object.id)} · ${prediction ? riskNames[prediction.risk] ?? 'Прогноз' : 'Нет прогноза'} · демокоординаты`;
      element.setAttribute('aria-label', element.title);
      element.disabled=!prediction&&!canSelectObject;
      element.addEventListener('click', event => {
        event.stopPropagation();
        const handlers = selectionHandlers.current;
        if (handlers.onObjectSelect) handlers.onObjectSelect(object);
        else if (prediction) (handlers.onFocus ?? handlers.onSelect)(prediction);
      });
      return new maplibregl.Marker({element, anchor: 'center'}).setLngLat([object.lon, object.lat]).addTo(map);
    });
    return () => {objectMarkers.current.forEach(marker => marker.remove()); objectMarkers.current = [];};
  }, [objects, predictionsByObject, selectedId, canSelectObject, focusedObjectId, mapAttempt]);
  useEffect(() => {
    const map=mapRef.current;
    if(!mapReady||!map?.getLayer('demo-route-selected'))return;
    const point=selectedCamera?.coordinate??(selectedObject && Number.isFinite(selectedObject.lat) && Number.isFinite(selectedObject.lon)?[selectedObject.lon,selectedObject.lat]:null);
    const nearest=point?ROUTES.map((route,id)=>({id,distance:Math.min(...route.points.map(p=>(p[0]-point[0])**2+(p[1]-point[1])**2))})).sort((a,b)=>a.distance-b.distance)[0].id:-1;
    map.setFilter('demo-route-selected',['==',['get','id'],nearest]);
  },[selectedCamera,selectedObject,mapReady]);
  useEffect(() => {
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450;
    if (selectedCamera) mapRef.current?.flyTo({center: selectedCamera.coordinate, zoom: Math.max(mapRef.current.getZoom(), 13), duration});
    else if (selectedObject && Number.isFinite(selectedObject.lat) && Number.isFinite(selectedObject.lon)) mapRef.current?.flyTo({center: [selectedObject.lon,selectedObject.lat], duration});
  }, [selectedCamera, selectedObject, mapReady]);

  return <div className={`map underground-map${large ? ' large' : ''}`}>
    <div ref={containerRef} className={`underground-map__canvas${mapReady ? ' is-ready' : ''}`} aria-label="Интерактивная векторная карта Москвы"/>
    <div className="underground-map__topbar"><span><MapPin size={13}/> МОСКВА / ВЕКТОРНАЯ КАРТА</span><button type="button" aria-pressed={showRoutes} onClick={() => setShowRoutes(value => !value)}><Layers3 size={14}/> Условные трассы</button><button type="button" aria-pressed={showCameras} onClick={() => setShowCameras(value => !value)}><Camera size={14}/> Камеры <b>{CAMERAS.length}</b></button><button type="button" onClick={() => {if (mapRef.current) frameNetwork(mapRef.current);}} aria-label="Показать всю сеть"><RotateCcw size={14}/> Вся сеть</button></div>
    {!mapReady && !mapError && <div className="underground-map__error" role="status">Загружаем карту Москвы…</div>}
    {mapError && <div className="underground-map__error" role="status"><span>{mapReady ? 'Часть карты не загрузилась.' : 'Не удалось загрузить карту.'} Список объектов и прогнозы доступны в рабочем месте.</span><button type="button" onClick={() => setMapAttempt(value => value + 1)}>Повторить загрузку</button></div>}
    {selectedCamera && <aside className="underground-camera-view" aria-label={`Макет камеры ${selectedCamera.id}`}>
      <div className="underground-camera-view__head"><span><Camera size={15}/> {selectedCamera.id} / {selectedCamera.group}</span><button type="button" aria-label="Закрыть камеру" onClick={() => setSelectedCameraId(null)}><X size={17}/></button></div>
      <div className="underground-camera-view__scene"><span>ИЛЛЮСТРАЦИЯ / ДЕМО</span><img src="/collector-tunnel.webp" alt="Иллюстрация подземного тоннеля, не трансляция"/></div>
      <strong>{selectedCamera.place}</strong><p>Положение условное. Видеопоток не подключён.</p>
      <div className="underground-camera-view__nearby"><span>КАМЕРЫ ВЕТВИ</span>{CAMERAS.filter(camera => camera.group === selectedCamera.group).map(camera => <button type="button" key={camera.id} aria-pressed={camera.id === selectedCamera.id} onClick={() => setSelectedCameraId(camera.id)}>{camera.id} <small>{camera.place}</small></button>)}</div>
    </aside>}
    <div className="underground-map__footer">
      <div className="map-legend"><span className="dot high"/> Высокий риск <span className="dot medium"/> Повышенный <span className="underground-map__legend-camera"/> Камера</div>
      <div className="map-caption">Нажмите тоннель или камеру · трассы, объекты и камеры — макет</div>
    </div>
  </div>;
}
