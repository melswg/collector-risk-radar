"""Stored channel forecast and dispatcher decision over the real HTTP API."""

import json
from pathlib import Path


def test_channel_events_to_saved_ml_forecast_and_decision(client):
    fixture = json.loads(Path('tests/fixtures/ml_channel_example.json').read_text())
    passport = {key: fixture['channel'][key] for key in (
        'sensor_type', 'engineering_system', 'object_kind', 'parent', 'synthetic',
    )}
    registered = client.put('/api/v1/sensors/7/ml-passport', json=passport)
    assert registered.status_code == 200, registered.text
    events = [{
        'id': f'ml-example-{index}', 'channel_id': 7,
        'ts': row['timestamp'], 'value': row['value'], 'тревожное': row['alarm'],
    } for index, row in enumerate(fixture['history'])]
    events.append({
        'id': 'ml-example-future', 'channel_id': 7,
        'ts': '2026-08-01T13:10:00Z', 'value': '1.4', 'тревожное': True,
    })
    ingested = client.post('/api/v1/ingest/events', json={'events': events})
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()['accepted'] == len(events)

    body = {'channel_id': 7, 'as_of': fixture['as_of'], 'request_id': 'ml-example'}
    response = client.post('/api/v1/predictions/ml-channel/run', json=body)
    assert response.status_code == 200, response.text
    prediction = response.json()
    assert prediction['object_id'] == 'obj-000001'
    assert prediction['incident_type'] == 'new_alarm_24h'
    assert prediction['model_kind'] == prediction['provider'] == 'ml'
    assert prediction['risk'] == 'unrated'
    assert prediction['extra']['feature_count'] == 19
    assert prediction['extra']['probability_calibrated'] is True
    assert prediction['extra']['threshold'] is None
    assert abs(prediction['probability'] - 0.03470437017994859) < 1e-9
    assert 'future_alarm' not in str(prediction).lower()
    assert client.post('/api/v1/predictions/ml-channel/run', json=body).json()['id'] == prediction['id']
    assert client.get('/api/v1/predictions').json()['items'][0]['id'] == prediction['id']

    decision = client.post('/api/v1/predictions/' + prediction['id'] + '/decision', json={
        'action': 'monitor', 'reason': 'confirmed_signals',
        'comment': 'Проверить показания канала в следующую смену', 'outcome': 'monitoring',
    })
    assert decision.status_code == 200, decision.text
    assert client.get('/api/v1/predictions/' + prediction['id']).json()['decisions'][0]['id'] == decision.json()['id']
