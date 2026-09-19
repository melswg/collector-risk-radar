"""Обновление витрин и архивирование с сохранением истории."""
from datetime import timedelta
from sqlalchemy import text, select
from backend.db import Record, Session, Object, now
from backend.context import ContextBuilder

with Session.begin() as session:
    timestamp = now()
    for obj in session.scalars(select(Object)):
        context = ContextBuilder(session).build([obj.id], timestamp).objects[0]
        for channel in context.channels:
            session.merge(Record(id=f'health:{channel.channel_id}:{timestamp:%Y%m%d%H}', kind='sensor_health', object_id=obj.id, ts=timestamp, data={'channel_id': channel.channel_id, **channel.health}))
    if session.bind.dialect.name == 'postgresql':
        session.execute(text('REFRESH MATERIALIZED VIEW ml.channel_agg_5m'))
        session.execute(text('REFRESH MATERIALIZED VIEW ml.channel_agg_1h'))
        session.execute(text('INSERT INTO archive.events SELECT * FROM public.events WHERE ts < :cutoff ON CONFLICT DO NOTHING'), {'cutoff': timestamp-timedelta(days=90)})
