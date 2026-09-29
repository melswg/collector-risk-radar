"""Customer CSV registry can supply a real ML passport without coordinates."""

from backend.db import Channel, Object, Record, Session


def test_customer_registry_and_journal_to_ml_http(client):
    objects = (
        'ид_объект,иерархия_уровень,родитель,вид_объекта,диспетчерское_название_объекта\n'
        '5333,3,5327,controlHouse,ДУ объект Альфа\n'
    ).encode()
    channels = (
        'ид_канала_данных,тип_инж_системы,тип_датчика,тег_инженерной_системы,название_датчика,ид_объект\n'
        '230543,Газовая охрана,Газовый датчик,15-11.1.131.2.,ГД ПК28,5333\n'
    ).encode()
    for kind, content in [('objects', objects), ('channels', channels)]:
        response = client.post('/api/v1/import/files', params={'kind': kind}, files={
            'file': (f'{kind}.csv', content, 'text/csv'),
        })
        assert response.status_code == 200, response.text
        assert response.json()['data']['accepted'] == 1, response.text

    with Session.begin() as session:
        obj = session.get(Object, '5333')
        assert obj.lat is None and obj.lon is None
        assert session.get(Channel, 230543).object_id == '5333'
        passport = session.get(Record, 'ml-passport:230543').data
        assert passport['sensor_type'] == 'Газовый датчик'
        assert passport['parent'] == '5327'
        assert passport['synthetic'] is False

    geojson = client.get('/api/v1/objects/geojson').json()
    assert all(feature['id'] != '5333' for feature in geojson['features'])
    events = [
        {'ид_события': 'customer-1', 'ид_канала_данных': '230543', 'дата': '2026-08-01', 'время': '07:30:00', 'тревожное': False, 'значение_датчика': '0.01'},
        {'ид_события': 'customer-2', 'ид_канала_данных': '230543', 'дата': '2026-08-01', 'время': '08:30:00', 'тревожное': False, 'значение_датчика': '0.02'},
    ]
    ingested = client.post('/api/v1/ingest/events', json={'events': events})
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()['accepted'] == 2
    predicted = client.post('/api/v1/predictions/ml-channel/run', json={
        'channel_id': 230543, 'as_of': '2026-08-01T08:59:59+03:00',
    })
    assert predicted.status_code == 200, predicted.text
    result = predicted.json()
    assert result['provider'] == result['model_kind'] == 'ml'
    assert result['object_id'] == '5333'
    assert result['extra']['feature_count'] == 19
    assert result['extra']['synthetic'] is False
    assert result['extra']['probability_calibrated'] is True
    assert 0 <= result['probability'] <= 1
