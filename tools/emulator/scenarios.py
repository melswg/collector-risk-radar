"""Сценарии для демонстрации без управления оборудованием."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from backend.db import Channel, Event, Object, Record, now


def inject_scenario(session, scenario):
    object_id = 'obj-000001' if scenario == 'fire' else 'obj-000002'
    if session.get(Object, object_id) is None:
        raise ValueError('Сначала выполните seed')
    timestamp = now()
    channels = session.scalars(select(Channel).where(Channel.object_id == object_id)).all()
    for i in range(36):
        ts = timestamp-timedelta(minutes=(35-i)*5)
        for c in channels:
            values = {'temperature': 22+(i*1.5 if scenario == 'fire' else (i%5)/10), 'smoke': int(scenario == 'fire' and i>25), 'gas': 0, 'pump': i%2 if scenario == 'flood' else 0, 'phase': int(scenario != 'flood' or i<20), 'fan': 1, 'movement': 0, 'contact-unlock-norm': 0, 'switch': 1}
            value = values[c.type_code]
            warning = value > 45 if c.type_code == 'temperature' else value == 0 if c.type_code in ('phase', 'fan') else value > 0 and c.type_code not in ('switch',)
            session.add(Event(id='demo-'+str(uuid4()), channel_id=c.id, object_id=object_id, ts=ts, value=value, expected=False, event='Предупреждение' if warning else 'Норма', severity='warning' if warning else 'normal', raw={'synthetic': True}))
    if scenario == 'flood':
        for h in (3, 6, 12, 18):
            ts = timestamp+timedelta(hours=h)
            session.add(Record(id='weather-'+str(uuid4()), kind='weather', object_id=object_id, ts=ts, available_at=timestamp, data=dict(kind='forecast', ts=ts.isoformat(), published_at=timestamp.isoformat(), precip_mm=9, temp_c=12, humidity=93, pressure_hpa=998)))
    session.flush()
    return object_id
