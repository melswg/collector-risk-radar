"""Exercise the customer CSV archive through the HTTP API in a temporary database."""

import argparse
from collections import defaultdict
import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--channel', type=int, required=True)
    parser.add_argument('--as-of', type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    if args.as_of.tzinfo is None:
        parser.error('--as-of must include a UTC offset')

    with tempfile.TemporaryDirectory(prefix='collector-customer-check-') as temporary:
        password = 'temporary-verification-password'
        os.environ.update({
            'DATABASE_URL': f'sqlite:///{temporary}/check.db',
            'DATA_DIR': temporary, 'AUTH_MODE': 'demo',
            'DEMO_PASSWORD': password, 'JWT_SECRET': 'temporary-verification-secret-32-chars',
            'ML_SERVICE_TOKEN': 'temporary-verification-service-token',
            'COOKIE_SECURE': 'false',
        })
        from fastapi.testclient import TestClient
        from backend.api import app
        from backend.auth import seed_users
        from backend.db import Session, init_db
        from backend.ingestion import read_rows

        init_db()
        with Session.begin() as session:
            seed_users(session)
        with zipfile.ZipFile(args.archive, metadata_encoding='cp866') as source, TestClient(app) as client:
            login = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': password})
            login.raise_for_status()
            imported = {}
            for kind, name in (
                ('objects', 'справочник_объектов_диспетчер.csv'),
                ('channels', 'справочник_каналов_датчиков.csv'),
            ):
                content = source.read(f'archive/{name}')
                response = client.post('/api/v1/import/files', params={'kind': kind}, files={
                    'file': (name, content, 'text/csv'),
                })
                response.raise_for_status()
                result = response.json()['data']
                if result['errors']:
                    raise RuntimeError(f'{kind}: {result["errors"][:3]}')
                imported[kind] = result['accepted']

            journal = read_rows(source.read('archive/журнал_событий_пример.csv'), 'journal.csv')
            state_rows = read_rows(source.read('archive/справочник_состояний.csv'), 'states.csv')
            channel_rows = read_rows(source.read('archive/справочник_каналов_датчиков.csv'), 'channels.csv')
            state_flags = defaultdict(set)
            for row in state_rows:
                state_flags[(row['тип_датчика'], row['название_состояния'])].add(row['тревожное'])
            uncovered_types = sorted({row['тип_датчика'] for row in channel_rows} - {row['тип_датчика'] for row in state_rows})
            ambiguous_states = [list(key) for key, flags in state_flags.items() if len(flags) > 1]
            events = [row for row in journal if int(row['channel_id']) == args.channel]
            accepted = 0
            for start in range(0, len(events), 500):
                response = client.post('/api/v1/ingest/events', json={'events': events[start:start + 500]})
                response.raise_for_status()
                result = response.json()
                if result['errors']:
                    raise RuntimeError(f'events: {result["errors"][:3]}')
                accepted += result['accepted']
            if not accepted:
                raise RuntimeError('No events found for the channel')

            response = client.post('/api/v1/predictions/ml-channel/run', json={
                'channel_id': args.channel, 'as_of': args.as_of.isoformat(),
                'request_id': f'customer-archive-{args.channel}-{args.as_of.isoformat()}',
            })
            response.raise_for_status()
            prediction = response.json()
            decision = client.post(f'/api/v1/predictions/{prediction["id"]}/decision', json={
                'action': 'monitor', 'reason': 'confirmed_signals',
                'comment': 'Проверить показания канала и журнал', 'outcome': 'monitoring',
            })
            decision.raise_for_status()
            print(json.dumps({
                'registry_imported': imported, 'channel_events_imported': accepted,
                'journal_dates': sorted({row['дата'] for row in journal}),
                'state_dictionary_uncovered_types': uncovered_types,
                'state_dictionary_ambiguous_pairs': ambiguous_states,
                'prediction_id': prediction['id'], 'object_id': prediction['object_id'],
                'source': prediction['provider'], 'synthetic': prediction['extra']['synthetic'],
                'features': prediction['extra']['feature_count'],
                'probability': prediction['probability'],
                'forecast_from': prediction['extra']['forecast_from'],
                'valid_until': prediction['valid_until'],
                'decision_id': decision.json()['id'],
            }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
