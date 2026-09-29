"""Приём событий сам запускает расчёт по каналу, без кнопки в интерфейсе."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures('live_scoring')

FIXTURE = json.loads(Path('tests/fixtures/ml_channel_example.json').read_text())
PASSPORT_KEYS = ('sensor_type', 'engineering_system', 'object_kind', 'parent', 'synthetic')


def register_passport(client, channel_id=7, fixture=FIXTURE):
    passport = {key: fixture['channel'][key] for key in PASSPORT_KEYS}
    response = client.put(f'/api/v1/sensors/{channel_id}/ml-passport', json=passport)
    assert response.status_code == 200, response.text


def current_hour_moment():
    """Момент внутри текущего часа, строго раньше «сейчас»: не зависит от минуты запуска."""
    now = datetime.now(timezone.utc)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    elapsed = (now - hour_start).total_seconds()
    return hour_start + timedelta(seconds=min(60.0, max(1.0, elapsed / 2)))


def fixture_events(channel_id=7, fixture=FIXTURE):
    rows = [{
        'id': f'trigger-{channel_id}-{index}', 'channel_id': channel_id,
        'ts': row['timestamp'], 'value': row['value'], 'тревожное': row['alarm'],
    } for index, row in enumerate(fixture['history'])]
    rows.append({
        'id': f'trigger-{channel_id}-now', 'channel_id': channel_id,
        'ts': current_hour_moment().isoformat(), 'value': '1.4', 'тревожное': False,
    })
    return rows


def test_ingest_scores_channel_without_manual_run(client):
    register_passport(client)
    response = client.post('/api/v1/ingest/events', json={'events': fixture_events()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['errors'] == [], body['errors']
    assert body['channels'] == [7]
    assert body['scoring']['mode'] == 'inline'
    assert body['scoring']['scored'] == 1, body['scoring'].get('skipped_reasons') or body['scoring']

    items = client.get('/api/v1/predictions').json()['items']
    assert len(items) == 1
    prediction = items[0]
    assert prediction['provider'] == prediction['model_kind'] == 'ml'
    assert prediction['incident_type'] == 'new_alarm_24h'
    assert prediction['extra']['trigger'] == 'ingest'
    assert prediction['extra']['probability_calibrated'] is True
    assert prediction['extra']['feature_count'] == 19
    assert prediction['extra']['latency_ms'] is not None
    assert prediction['risk'] == 'unrated'


def test_repeated_ingest_does_not_duplicate_forecast(client):
    register_passport(client)
    events = fixture_events()
    assert client.post('/api/v1/ingest/events', json={'events': events}).json()['scoring']['scored'] == 1
    repeated = client.post('/api/v1/ingest/events', json={'events': events}).json()
    assert repeated['accepted'] == 0
    assert repeated['channels'] == []
    assert repeated['scoring']['mode'] == 'skipped'
    assert len(client.get('/api/v1/predictions').json()['items']) == 1


def test_channel_without_passport_is_skipped_with_reason(client):
    response = client.post('/api/v1/ingest/events', json={'events': fixture_events(channel_id=8)})
    assert response.status_code == 200, response.text
    report = response.json()['scoring']
    assert report['scored'] == 0
    assert report['skipped'] == 1
    assert 'ML-паспорт' in next(iter(report['skipped_reasons']))
    assert client.get('/api/v1/predictions').json()['items'] == []


def test_alarm_in_scored_hour_is_skipped(client):
    register_passport(client)
    events = fixture_events()
    events.append({
        'id': 'trigger-alarm-now', 'channel_id': 7,
        'ts': current_hour_moment().isoformat(), 'value': '0.4', 'тревожное': True,
    })
    report = client.post('/api/v1/ingest/events', json={'events': events}).json()['scoring']
    assert report['scored'] == 0
    assert 'тревожном часу' in next(iter(report['skipped_reasons']))


def test_candidate_channels_uses_scored_hour(populated):
    from backend.db import Event
    from backend.jobs import candidate_channels
    from backend.ml_channel import feature_hour_for

    as_of = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    hour = feature_hour_for(as_of)
    assert hour == datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    populated.add(Event(id='hour-in', channel_id=7, object_id='obj-000001',
                        ts=hour + timedelta(minutes=20), value=1.0, raw={}))
    populated.add(Event(id='hour-out', channel_id=8, object_id='obj-000001',
                        ts=hour - timedelta(hours=3), value=1.0, raw={}))
    populated.flush()
    assert candidate_channels(populated, as_of) == [7]
