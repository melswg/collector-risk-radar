"""Исполняемый контрактный стенд. Поддерживает rules и явно помеченный stub."""
import hashlib
import json
import os
import secrets
from pathlib import Path
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from backend.contracts import PredictRequest, TrainJob, validate_response
from backend.prediction_providers.rules import RulesProvider
from ml_service_template.predictor import predict_batch
from ml_service_template.trainer import train

app = FastAPI(title='ML contract v1.0 — STUB', version='1.0')
STORE = Path(os.getenv('ML_STORE', 'data/ml-service'))
STORE.mkdir(parents=True, exist_ok=True)
TOKEN = os.getenv('ML_SERVICE_TOKEN')
if not TOKEN:
    raise RuntimeError('Требуется ML_SERVICE_TOKEN')


def auth(authorization: str = Header(default='')):
    if not secrets.compare_digest(authorization, 'Bearer '+TOKEN):
        raise HTTPException(401, 'Сервисный токен неверен')


def path(key):
    return STORE/(hashlib.sha256(key.encode()).hexdigest()+'.json')


def save(key, value):
    target = path(key)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False))
    temp.replace(target)


def read(key):
    target = path(key)
    if not target.exists():
        raise HTTPException(404, 'Не найдено')
    return json.loads(target.read_text())

@app.get('/v1/health', dependencies=[Depends(auth)])
def health():
    return {'status': 'ready', 'contract_version': '1.0', 'kind': os.getenv('TEMPLATE_PROVIDER', 'stub')}

@app.get('/v1/models', dependencies=[Depends(auth)])
def models():
    if os.getenv('TEMPLATE_PROVIDER') == 'rules':
        return RulesProvider().list_models()
    if path('models').exists():
        return read('models')
    return [{'id': 'stub', 'version': '1.0', 'kind': 'stub', 'status': 'active', 'incident_types': ['fire', 'flood', 'intrusion_false_alarm', 'sensor_failure'], 'horizons_h': [24, 72], 'trained_at': None, 'metrics': {}, 'data_manifest_id': None}]

@app.post('/v1/predict', dependencies=[Depends(auth)])
def predict(request: PredictRequest):
    digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    key = 'predict:'+request.request_id
    if path(key).exists():
        cached = read(key)
        if cached['digest'] != digest:
            raise HTTPException(409, 'request_id уже занят другим запросом')
        return cached['response']
    known = set(os.getenv('ML_KNOWN_OBJECTS', '').split(','))-{''}
    unknown = [o.object_id for o in request.objects if known and o.object_id not in known]
    filtered = request.model_copy(update={'objects': [o for o in request.objects if o.object_id not in unknown]})
    result = RulesProvider().predict(filtered) if os.getenv('TEMPLATE_PROVIDER') == 'rules' else predict_batch(filtered)
    from backend.contracts import ObjectError
    result.errors.extend(ObjectError(object_id=o, code='unknown_object', message='Объект отсутствует в реестре') for o in unknown)
    validate_response(request, result)
    response = result.model_dump(mode='json')
    save(key, {'digest': digest, 'response': response})
    return response


def run_job(kind, identity, body):
    save(kind+identity, {'id': identity, 'status': 'running', 'progress': 0.1, 'log_tail': []})
    try:
        result = predict(PredictRequest.model_validate(body)) if kind == 'predict:' else train(TrainJob.model_validate(body))
        save(kind+identity, {'id': identity, 'status': 'succeeded', 'progress': 1.0, 'log_tail': ['STUB' if kind == 'train:' else 'Расчёт завершён'], 'result': result, 'model': result if kind == 'train:' else None})
        if kind == 'train:':
            registry = models()
            registry.append({**result, 'status': 'active' if body.get('activate_on_success') else 'inactive'})
            save('models', registry)
            model_dir = STORE/'models'/result['id']/hashlib.sha256(result['version'].encode()).hexdigest()[:16]
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir/'metadata.json').write_text(json.dumps(result))
    except Exception as exc:
        save(kind+identity, {'id': identity, 'status': 'failed', 'progress': 1.0, 'log_tail': [type(exc).__name__]})

@app.post('/v1/predict/jobs', dependencies=[Depends(auth)])
def predict_job(body: PredictRequest, tasks: BackgroundTasks):
    key = 'predict:'+body.request_id+':job'
    if path(key).exists():
        return read(key)
    save(key, {'id': body.request_id+':job', 'status': 'queued', 'progress': 0})
    tasks.add_task(run_job, 'predict:', body.request_id+':job', body.model_dump(mode='json'))
    return read(key)

@app.get('/v1/predict/jobs/{identity}', dependencies=[Depends(auth)])
def prediction_job_status(identity: str):
    return read('predict:'+identity)

@app.post('/v1/train/jobs', dependencies=[Depends(auth)])
def training_job(body: TrainJob, tasks: BackgroundTasks):
    if path('train:'+body.job_id).exists():
        return read('train:'+body.job_id)
    save('train:'+body.job_id, {'id': body.job_id, 'status': 'queued', 'progress': 0})
    tasks.add_task(run_job, 'train:', body.job_id, body.model_dump(mode='json'))
    return read('train:'+body.job_id)

@app.get('/v1/train/jobs/{identity}', dependencies=[Depends(auth)])
def training_status(identity: str):
    return read('train:'+identity)

@app.post('/v1/models/{identity}/activate', dependencies=[Depends(auth)])
def activate(identity: str):
    return set_status(identity, 'active')

@app.post('/v1/models/{identity}/shadow', dependencies=[Depends(auth)])
def shadow(identity: str):
    return set_status(identity, 'shadow')


def set_status(identity, status):
    registry = models()
    matches = [m for m in registry if m['id'] == identity or m['id']+'@'+m['version'] == identity]
    if not matches:
        raise HTTPException(404, 'Модель не найдена')
    chosen = matches[-1]
    for m in registry:
        if status == 'active' and m.get('status') == 'active':
            m['status'] = 'inactive'
    chosen['status'] = status
    save('models', registry)
    return chosen
