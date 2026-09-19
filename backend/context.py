"""Контекст на момент as_of: будущие наблюдения и публикации исключаются."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from backend.analytics import sensor_health
from backend.contracts import PredictRequest
from backend.db import Channel, Event, Object, Record, serialize, utc
from backend.settings import config

class ContextBuilder:
    def __init__(self, session):
        self.session = session

    def build(self, object_ids, as_of, horizons=None, what_if=None, request_id=None):
        settings = config('settings')
        saved = self.session.get(Record, 'settings')
        if saved:
            settings.update(saved.data)
        objects = []
        for object_id in object_ids:
            obj = self.session.get(Object, object_id)
            if obj is None:
                raise ValueError(f'Неизвестный объект: {object_id}')
            events = self.session.scalars(select(Event).where(Event.object_id == obj.id, Event.ts <= as_of, Event.ts >= as_of-timedelta(hours=settings['context_hours'])).order_by(Event.ts)).all()
            channels = self.session.scalars(select(Channel).where(Channel.object_id == obj.id)).all()
            records = self.session.scalars(select(Record).where(Record.object_id == obj.id, Record.available_at <= as_of)).all()
            weather = [r for r in records if r.kind == 'weather']
            channel_contexts = []
            for c in channels:
                points = [(utc(e.ts), e.value) for e in events if e.channel_id == c.id]
                neighbors = [e.value for e in events if e.channel_id != c.id and e.channel_id in [n.id for n in channels if n.type_code == c.type_code] and utc(e.ts) >= as_of-timedelta(hours=1)]
                health = sensor_health(points, as_of, c.type_code, neighbor_mean=sum(neighbors)/len(neighbors) if neighbors else None)
                channel_contexts.append(dict(channel_id=c.id, type_id=c.type_id, type_code=c.type_code, series={'points': points, 'from': (as_of-timedelta(hours=settings['context_hours'])).isoformat(), 'to': as_of.isoformat()}, health=health))
            observed = [r.data for r in weather if r.data.get('kind') == 'observed' and as_of-timedelta(hours=24) <= utc(r.ts) <= as_of]
            forecast = [r.data for r in weather if r.data.get('kind') == 'forecast' and as_of < utc(r.ts) <= as_of+timedelta(hours=max(horizons or settings['horizons_h']))]
            # Для каждого срока берём последнюю доступную публикацию, исключая двойной счёт осадков.
            unique = {}
            for w in sorted(forecast, key=lambda x: x['published_at']):
                unique[w['ts']] = w
            works = [r.data for r in records if r.kind == 'work']
            historical_floods = sum(r.kind == 'label' and r.data.get('incident_type') == 'flood' and utc(r.ts) < as_of for r in records)
            objects.append(dict(object_id=obj.id, tag=obj.tag, hierarchy=[settings['hierarchy_separator'].join(obj.tag.split(settings['hierarchy_separator'])[:i]) for i in range(1, len(obj.tag.split(settings['hierarchy_separator']))+1)], geo={'lat': obj.lat, 'lon': obj.lon}, meta=obj.meta, channels=channel_contexts, recent_alarms=[{**serialize(e), 'ts': utc(e.ts).isoformat()} for e in events if e.severity == 'warning' and utc(e.ts) >= as_of-timedelta(hours=6)], planned_works=works, maintenance={'last_service_at': obj.meta.get('last_service_at'), 'open_orders': sum(w.get('status') in ('approved', 'in_progress') for w in works), 'flood_history': historical_floods}, weather={'observed': observed, 'forecast': list(unique.values())} if settings['weather_enabled'] else {}))
        return PredictRequest.model_validate(dict(request_id=request_id or str(uuid4()), as_of=as_of, objects=objects, horizons_h=horizons or settings['horizons_h'], options={'what_if': what_if}))
