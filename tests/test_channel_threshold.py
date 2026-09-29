"""Порог каналового прогноза и уведомление по нему."""

import pytest

from test_channel_trigger import current_hour_moment, fixture_events, register_passport  # noqa: E402

pytestmark = pytest.mark.usefixtures('live_scoring')


def enable_threshold(client, threshold, notify):
    from backend.db import Record, Session
    with Session.begin() as session:
        session.merge(Record(id='settings', kind='settings', data={
            'ml_channel_threshold': threshold, 'ml_channel_notify': notify,
        }))
    return client


def test_threshold_sets_risk_and_queues_notification(client):
    enable_threshold(client, 0.0, True)
    register_passport(client)
    body = client.post('/api/v1/ingest/events', json={'events': fixture_events()}).json()
    assert body['scoring']['scored'] == 1

    prediction = client.get('/api/v1/predictions').json()['items'][0]
    assert prediction['extra']['threshold'] == 0.0
    assert prediction['risk'] == 'medium'
    assert prediction['extra']['notification_id']

    notifications = client.get('/api/v1/notifications').json()
    rows = notifications if isinstance(notifications, list) else notifications['items']
    assert any(row['data']['prediction_id'] == prediction['id'] for row in rows)


def test_threshold_without_notifications_stays_quiet(client):
    enable_threshold(client, 0.0, False)
    register_passport(client)
    client.post('/api/v1/ingest/events', json={'events': fixture_events()})

    prediction = client.get('/api/v1/predictions').json()['items'][0]
    assert prediction['risk'] == 'medium'
    assert 'notification_id' not in prediction['extra']
    notifications = client.get('/api/v1/notifications').json()
    rows = notifications if isinstance(notifications, list) else notifications['items']
    assert rows == []


def test_probability_below_threshold_keeps_channel_normal(client):
    enable_threshold(client, 0.99, True)
    register_passport(client)
    client.post('/api/v1/ingest/events', json={'events': fixture_events()})

    prediction = client.get('/api/v1/predictions').json()['items'][0]
    assert prediction['extra']['threshold'] == 0.99
    assert prediction['risk'] == 'normal'
    assert 'notification_id' not in prediction['extra']
