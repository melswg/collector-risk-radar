import json
import os
import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
import httpx
import jsonschema
import pytest
from backend.contracts import PredictRequest,PredictResponse,validate_response
from backend.prediction_providers.rules import RulesProvider

def payload(empty=False):
    t=datetime(2026,9,19,tzinfo=timezone.utc)
    return {'contract_version':'1.0','request_id':str(uuid4()),'as_of':t.isoformat(),'horizons_h':[24,72],'incident_types':['fire','flood','intrusion_false_alarm','sensor_failure'],'objects':[{'object_id':'obj-000001','tag':'МК-1.1','channels':[{'channel_id':12,'type_id':12,'type_code':'temperature','series':{'points':[] if empty else [[(t-timedelta(minutes=5*i)).isoformat(),25+i*.1] for i in range(12,0,-1)]},'health':{'status':'ok'}}]}]}

@pytest.fixture(params=['rules','stub'])
def service(request):
    remote=request.config.getoption('--ml-url')
    if remote:
        client=httpx.Client(base_url=remote,headers={'Authorization':'Bearer '+os.getenv('ML_SERVICE_TOKEN','')},timeout=300)
        return lambda data:client.post('/v1/predict',json=data).json(),client
    if request.param=='rules':
        return lambda data:RulesProvider().predict(PredictRequest.model_validate(data)).model_dump(mode='json'),None
    from fastapi.testclient import TestClient
    from ml_service_template.app import app
    client=TestClient(app,headers={'Authorization':'Bearer '+os.environ['ML_SERVICE_TOKEN']})
    return lambda data:client.post('/v1/predict',json=data).json(),client

def test_schema_idempotency_horizons(service):
    call,_=service;body=payload();body['future_optional_field']='accepted'
    start=time.monotonic();first=call(body)
    assert time.monotonic()-start<300
    jsonschema.validate(first,json.loads(Path('contracts/ml/predict_response.schema.json').read_text()))
    validate_response(PredictRequest.model_validate(body),PredictResponse.model_validate(first))
    assert len(first['predictions'])==8 and first==call(body)
    assert all(p['probability'] is None or 0<=p['probability']<=1 for p in first['predictions'])

def test_empty(service):
    result=service[0](payload(True))
    assert all(p['data_sufficiency']=='insufficient' and p['probability'] is None for p in result['predictions'])

def test_async_health(service):
    _,client=service
    if client is None:
        assert RulesProvider().health()['status']=='ready'
        return
    assert client.get('/v1/health').status_code==200
    assert client.get('/v1/models').json()
    job=client.post('/v1/predict/jobs',json=payload()).json()
    for _ in range(50):
        status=client.get('/v1/predict/jobs/'+job['id']).json()
        if status['status'] in ['succeeded','failed']:
            break
        time.sleep(.1)
    assert status['status']=='succeeded',status

def test_unknown(monkeypatch):
    from fastapi.testclient import TestClient
    from ml_service_template.app import app
    monkeypatch.setenv('ML_KNOWN_OBJECTS','obj-known')
    with TestClient(app,headers={'Authorization':'Bearer '+os.environ['ML_SERVICE_TOKEN']}) as client:
        response=client.post('/v1/predict',json=payload())
        assert response.status_code==200 and response.json()['errors'][0]['code']=='unknown_object'
        assert not response.json()['predictions']
