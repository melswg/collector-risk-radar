import os
from datetime import timedelta
from backend.db import now

def test_auth_rbac(client):
    assert client.get('/api/v1/admin/users').status_code==200
    client.post('/api/v1/auth/logout')
    assert client.get('/api/v1/objects').status_code==401
    assert client.post('/api/v1/auth/login',json={'username':'dispatcher','password':os.environ['DEMO_PASSWORD']}).status_code==200
    assert client.get('/api/v1/admin/users').status_code==403
    assert client.put('/api/v1/settings',json={'ml_mode':'http'}).status_code==403
    assert client.get('/api/v1/predictions?role=shadow').status_code==403

def test_audit_after_writing_request(client):
    from sqlalchemy import select
    from backend.db import Audit, Session

    response = client.post('/api/v1/demo/fire', json={})
    assert response.status_code == 200, response.text
    with Session() as session:
        entry = session.scalars(select(Audit).where(Audit.path == '/api/v1/demo/fire')).one()
        assert entry.username == 'admin'
        assert entry.status == 200

def test_fire_flood_decisions(client):
    for scenario in ['fire','flood']:
        response=client.post('/api/v1/demo/'+scenario,json={})
        assert response.status_code==200,response.text
        p=next(p for p in response.json()['items'] if p['incident_type']==scenario)
        assert p['probability']>.75
        identity=p['id']
        assert client.post('/api/v1/predictions/'+identity+'/decision',json={'action':'dispatch','reason':'bad','comment':'Тест'}).status_code==422
        valid=client.post('/api/v1/predictions/'+identity+'/decision',json={'action':'inspect','reason':'confirmed_signals','comment':'Проверены сопутствующие сигналы','outcome':'monitoring'})
        assert valid.status_code==200,valid.text
        assert client.get('/api/v1/predictions/'+identity).json()['decisions']
        assert client.get('/api/v1/predictions/'+identity+'/analogs').status_code==200
    assert client.get('/api/v1/notifications').json()['total']>=2
    assert client.get('/api/v1/recommendations').json()['total']>=2
    assert client.get('/api/v1/objects/geojson').json()['features']
    assert client.get('/api/v1/sensors/12/health').status_code==200
    assert client.get('/api/v1/sensors/12/series').json()['total']>0
    assert client.post('/api/v1/predictions/what-if',json={'object_ids':['obj-000002'],'precip_mm_delta':10}).status_code==200

def test_import_export_settings(client):
    content='id;channel_id;value;ts\na;12;25,00;19.09.2026 12:15\n'.encode()
    first=client.post('/api/v1/import/files',files={'file':('sample.csv',content,'text/csv')})
    assert first.status_code==200,first.text
    assert client.post('/api/v1/import/files',files={'file':('sample.csv',content,'text/csv')}).json()['duplicate_file']
    assert client.get('/api/v1/import/jobs/'+first.json()['id']).status_code==200
    assert client.put('/api/v1/settings',json={'risk_thresholds':{'low':.9,'medium':.5,'high':.1}}).status_code==422
    assert client.put('/api/v1/settings',json={'risk_thresholds':{'low':.2,'medium':.4,'high':.7}}).status_code==200
    assert client.get('/api/v1/reports/predictions?format=xlsx').status_code==200
    assert client.post('/api/v1/feedback/export',json={}).status_code==200
    assert client.get('/api/v1/admin/audit').json()['total']>0


def test_ml_journal_csv_upload(client):
    from backend.db import Channel, Session

    with Session.begin() as session:
        session.add(Channel(id=120473, object_id='obj-000001', type_id=5, type_code='movement'))
    content = ('"ид_события","ид_канала_данных","дата","время","тревожное","значение_датчика"\n'
               '4524243389,120473,"2026-08-01","03:09:27",false,"28"\n'
               '4524243390,120473,"2026-08-01","03:10:27",true,"Неопределен"\n').encode()
    response = client.post('/api/v1/import/files', files={'file': ('journal.csv', content, 'text/csv')})
    assert response.status_code == 200, response.text
    assert response.json()['data']['accepted'] == 2
    assert response.json()['data']['errors'] == []
    events = client.get('/api/v1/events?object_id=obj-000001').json()['items']
    text_state = next(event for event in events if event['id'] == '4524243390')
    assert text_state['value'] is None
    assert text_state['raw']['value'] == 'Неопределен'

def test_xml_pii(client):
    xml='<events><event><id>xml1</id><channel_id>12</channel_id><value>25,00</value><ts>19.09.2026 12:15</ts></event></events>'
    assert client.post('/api/v1/ingest/events',content=xml,headers={'Content-Type':'application/xml'}).json()['accepted']==1
    assert client.post('/api/v1/ingest/events',json=[{'id':'p','channel_id':12,'value':25,'ts':'19.09.2026 12:15','comment':'user@example.com'}]).status_code==422

def test_shadow_work_suppression(client,monkeypatch):
    from backend.api import provider
    from backend.db import Session,Record
    from backend.prediction_providers.rules import RulesProvider
    provider.mode='shadow';monkeypatch.setattr(provider.remote,'predict',RulesProvider().predict)
    with Session.begin() as s:
        s.add(Record(id='work1',kind='work',object_id='obj-000001',available_at=now()-timedelta(hours=2),data={'from':(now()-timedelta(hours=1)).isoformat(),'to':(now()+timedelta(hours=1)).isoformat(),'status':'approved'}))
    r=client.post('/api/v1/demo/fire',json={})
    assert r.status_code==200,r.text
    assert any(p['role']=='shadow' for p in r.json()['items'])
    assert all(p['role']=='active' for p in client.get('/api/v1/predictions').json()['items'])
    assert client.get('/api/v1/notifications').json()['total']==0
