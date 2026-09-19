"""Загрузка датасета и подготовка обоих демо-сценариев."""
import json
from datetime import timedelta
import pandas as pd
from sqlalchemy import select
from backend.auth import seed_users
from backend.db import Channel, Event, Object, Record, Session, init_db, now
from backend.ingestion import ingest_registry, parse_date
from backend.settings import DATA
from tools.synth.generate import generate
from tools.emulator.scenarios import inject_scenario


def seed():
    init_db()
    folder = DATA/'synthetic-small'
    if not (folder/'manifest.json').exists():
        generate(folder)
    with Session.begin() as session:
        seed_users(session)
        if session.scalar(select(Object.id).limit(1)):
            return
        objects = pd.read_parquet(folder/'objects.parquet').to_dict('records')
        for obj in objects:
            obj['meta'] = json.loads(obj['meta'])
        ingest_registry(session, objects, 'objects')
        ingest_registry(session, pd.read_parquet(folder/'channels.parquet').to_dict('records'), 'channels')
        channels = {c.id: c for c in session.scalars(select(Channel))}
        # Синтетика уже типизирована; пакетная запись ускоряет первый запуск.
        events = []
        for e in pd.read_parquet(folder/'events.parquet').to_dict('records'):
            channel = channels[e['channel_id']]
            alarm = e['value'] > 45 if channel.type_code == 'temperature' else e['value'] < 0.5 if channel.type_code in ('phase', 'fan') else e['value'] > 0.5
            events.append(dict(id=e['id'], channel_id=e['channel_id'], object_id=channel.object_id, ts=parse_date(e['ts']), value=e['value'], expected=False, event='Предупреждение' if alarm else 'Норма', severity='warning' if alarm else 'normal', raw={'synthetic': True}))
        session.bulk_insert_mappings(Event, events)
        for name, kind in [('labels', 'label'), ('weather', 'weather'), ('planned_works', 'work')]:
            for i, row in enumerate(pd.read_parquet(folder/f'{name}.parquet').to_dict('records')):
                row = {k: v for k, v in row.items() if not isinstance(v, float) or not pd.isna(v)}
                ts = parse_date(row.get('ts', row.get('start_ts', row.get('from'))))
                session.add(Record(id=f'{kind}:{i}', kind=kind, object_id=row['object_id'], ts=ts, available_at=parse_date(row.get('published_at', ts.isoformat())), data=row))
        manifest = json.loads((folder/'manifest.json').read_text())
        for obj in objects:
            session.add(Record(id='coverage:'+obj['id'], kind='coverage', object_id=obj['id'], data={**manifest['period'], 'synthetic': True}))
        inject_scenario(session, 'fire')
        inject_scenario(session, 'flood')
        session.flush()
        from backend.prediction_providers.http import ProviderRouter
        from backend.services import run_predictions
        run_predictions(session, ProviderRouter())
    print('Демо-данные загружены. Пожар: obj-000001; подтопление: obj-000002.')

if __name__ == '__main__':
    seed()
