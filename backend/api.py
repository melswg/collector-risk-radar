"""REST API, диспетчерские решения и аудит."""
import asyncio
import hashlib
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.staticfiles import StaticFiles
from backend.auth import current_user, login, require
from backend.context import ContextBuilder
from backend.contracts import TrainJob
from backend.db import Audit, Channel, Decision, Event, Object, Prediction, Record, Session, User, init_db, now, serialize, utc
from backend.ingestion import contains_pii, ingest_events, ingest_registry, parse_date, read_rows
from backend.ml_channel import run_channel_prediction
from backend.prediction_providers.base import NotSupported
from backend.prediction_providers.http import ProviderRouter
from backend.services import evaluate, run_predictions, settings
from backend.settings import DATA, ROOT, config

provider = ProviderRouter()

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title='Москоллектор — прогнозы и ТО', version='1.0.0', lifespan=lifespan)
api = '/api/v1'
rate_buckets = defaultdict(deque)

@app.middleware('http')
async def audit_and_security(request, call_next):
    key = (request.client.host if request.client else 'local', request.url.path == api+'/auth/login')
    bucket = rate_buckets[key]
    current = time.monotonic()
    while bucket and bucket[0] < current-60:
        bucket.popleft()
    if len(bucket) >= (15 if key[1] else 1200):
        response = JSONResponse({'error': {'code': 'rate_limit', 'message': 'Слишком много запросов'}}, status_code=429)
    elif request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('sec-fetch-site') == 'cross-site':
        response = JSONResponse({'error': {'code': 'csrf', 'message': 'Межсайтовый запрос запрещён'}}, status_code=403)
    else:
        bucket.append(current)
        response = await call_next(request)
    response.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin'})
    if request.url.path.startswith(api) and not request.url.path.endswith('/notifications/stream'):
        with Session.begin() as session:
            session.add(Audit(username=getattr(request.state, 'username', 'anonymous'), method=request.method, path=request.url.path, status=response.status_code, params={k: v for k, v in request.query_params.items() if k not in ('token', 'password')}))
    return response

@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error': {'code': str(exc.status_code), 'message': exc.detail}}, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': {'code': 'validation', 'message': 'Неверный формат данных', 'fields': [str(e['loc']) for e in exc.errors()]}}, status_code=422)

@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'error': {'code': 'validation', 'message': str(exc)}}, status_code=422)

@app.exception_handler(NotSupported)
async def unsupported(request, exc):
    return JSONResponse({'error': {'code': 'not_supported', 'message': str(exc)}}, status_code=409)


def db():
    with Session.begin() as session:
        yield session


def get_or_404(session, model, identity):
    item = session.get(model, identity)
    if item is None:
        raise HTTPException(404, 'Запись не найдена')
    return item


def page(session, query, limit=100, offset=0):
    if not 1 <= limit <= 1000 or offset < 0:
        raise HTTPException(422, 'Неверная пагинация')
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    return {'items': [serialize(r) for r in session.scalars(query.limit(limit).offset(offset))], 'total': total}

class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)

@app.post(api+'/auth/login')
def auth_login(body: LoginBody, response: Response, request: Request):
    token, user = login(body.username, body.password)
    request.state.username = user['username']
    response.set_cookie('session', token, httponly=True, samesite='strict', secure=os.getenv('COOKIE_SECURE', 'false') == 'true', max_age=3600)
    return {'access_token': token, 'token_type': 'bearer', 'user': user}

@app.post(api+'/auth/logout')
def logout(response: Response):
    response.delete_cookie('session')
    return {'ok': True}

@app.get(api+'/auth/me')
def me(user=Depends(current_user)):
    return {k: user[k] for k in ('username', 'role')}

@app.get('/health')
@app.get(api+'/health')
def health():
    with Session() as session:
        session.execute(select(1))
    return {'status': 'ok', 'prediction': provider.health()}

@app.get('/metrics')
@app.get(api+'/metrics')
def prometheus(user=Depends(require('admin'))):
    h = provider.health()
    return Response('\n'.join(f'moscollector_{k} {h[k]}' for k in ['calls', 'fallback_count', 'fallback_ratio', 'latency_seconds', 'contract_errors'])+'\n', media_type='text/plain')

@app.get(api+'/objects')
@app.get(api+'/equipment')
def objects(limit: int=100, offset: int=0, session=Depends(db, scope='function'), user=Depends(current_user)):
    return page(session, select(Object).order_by(Object.name), limit, offset)

@app.get(api+'/objects/geojson')
def geojson(session=Depends(db, scope='function'), user=Depends(current_user)):
    return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'id': o.id, 'geometry': {'type': 'Point', 'coordinates': [o.lon, o.lat]}, 'properties': {'id': o.id, 'name': o.name, 'tag': o.tag, 'wkt': f'POINT({o.lon} {o.lat})'}} for o in session.scalars(select(Object))]}

@app.get(api+'/objects/{identity}')
def object_detail(identity: str, session=Depends(db, scope='function'), user=Depends(current_user)):
    obj = get_or_404(session, Object, identity)
    context = ContextBuilder(session).build([identity], now()).objects[0]
    return {**serialize(obj), 'context': context.model_dump(mode='json')}

@app.get(api+'/sensors/{identity}/series')
def sensor_series(identity: int, start: datetime | None=None, end: datetime | None=None, session=Depends(db, scope='function'), user=Depends(current_user)):
    get_or_404(session, Channel, identity)
    query = select(Event).where(Event.channel_id == identity, Event.ts >= (start or now()-timedelta(hours=72)), Event.ts <= (end or now())).order_by(Event.ts)
    return page(session, query, 1000)

@app.get(api+'/sensors/{identity}/health')
def sensor_status(identity: int, session=Depends(db, scope='function'), user=Depends(current_user)):
    channel = get_or_404(session, Channel, identity)
    context = ContextBuilder(session).build([channel.object_id], now()).objects[0]
    return next(c.health for c in context.channels if c.channel_id == identity)

@app.post(api+'/ingest/events')
async def events_ingest(request: Request, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    raw = await request.body()
    if len(raw) > 10_000_000:
        raise HTTPException(413, 'Пакет слишком большой')
    if 'xml' in request.headers.get('content-type', ''):
        from defusedxml.ElementTree import fromstring
        rows = [{c.tag: c.text for c in row} for row in fromstring(raw)]
    else:
        payload = json.loads(raw)
        rows = payload if isinstance(payload, list) else payload['events']
    result = ingest_events(session, rows)
    return result

@app.post(api+'/registry/equipment/sync')
def registry_sync(body: dict, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    return ingest_registry(session, body['rows'], body.get('kind', 'objects'))

@app.post(api+'/ingest/ods-journal')
def ods(body: list[dict], session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    if contains_pii(body):
        raise ValueError('Обнаружены возможные персональные данные')
    for row in body:
        get_or_404(session, Object, row['object_id'])
        if row['incident_type'] not in ('fire', 'flood', 'intrusion', 'intrusion_false_alarm', 'sensor_failure'):
            raise ValueError('Неизвестный тип инцидента')
        ts = parse_date(row['start_ts'])
        session.merge(Record(id='ods:'+str(row['id']), kind='label', object_id=row['object_id'], ts=ts, available_at=now(), data={**row, 'source': 'ods'}))
    return {'accepted': len(body)}

@app.post(api+'/import/files')
async def file_import(kind: Literal['events', 'objects', 'channels', 'ods']='events', file: UploadFile=File(), session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    content = await file.read(20_000_001)
    if len(content) > 20_000_000:
        raise HTTPException(413, 'Файл больше 20 МБ')
    identity = hashlib.sha256(kind.encode()+content).hexdigest()
    existing = session.get(Record, identity)
    if existing:
        return {**serialize(existing), 'duplicate_file': True}
    rows = read_rows(content, file.filename or 'input.csv')
    result = ingest_events(session, rows) if kind == 'events' else ods(rows, session, user) if kind == 'ods' else ingest_registry(session, rows, kind)
    record = Record(id=identity, kind='import', data={'status': 'succeeded' if not result.get('errors') else 'partial', 'filename': file.filename, **result})
    session.add(record)
    session.flush()
    return serialize(record)

@app.get(api+'/import/jobs/{identity}')
def import_status(identity: str, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    return serialize(get_or_404(session, Record, identity))

@app.get(api+'/events')
def event_list(start: datetime | None=None, end: datetime | None=None, object_id: str | None=None, type_code: str | None=None, severity: str | None=None, sort: str='desc', limit: int=100, offset: int=0, session=Depends(db, scope='function'), user=Depends(current_user)):
    query = select(Event)
    if start:
        query = query.where(Event.ts >= start)
    if end:
        query = query.where(Event.ts <= end)
    if object_id:
        query = query.where(Event.object_id == object_id)
    if type_code:
        query = query.where(Event.channel_id.in_(select(Channel.id).where(Channel.type_code == type_code)))
    if severity:
        query = query.where(Event.severity == severity)
    return page(session, query.order_by(Event.ts.asc() if sort == 'asc' else Event.ts.desc()), limit, offset)

class RunBody(BaseModel):
    object_ids: list[str] | None = None
    as_of: datetime | None = None
    horizons_h: list[int] | None = None
    request_id: str | None = None

class MlPassportBody(BaseModel):
    sensor_type: str = Field(min_length=1, max_length=100)
    engineering_system: str = Field(min_length=1, max_length=100)
    object_kind: str = Field(min_length=1, max_length=100)
    parent: str = Field(min_length=1, max_length=100)
    synthetic: bool

@app.put(api+'/sensors/{identity}/ml-passport')
def ml_passport(identity: int, body: MlPassportBody, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    channel = get_or_404(session, Channel, identity)
    session.merge(Record(
        id=f'ml-passport:{identity}', kind='ml_channel_passport', object_id=channel.object_id,
        ts=now(), data=body.model_dump(),
    ))
    return {'channel_id': identity, 'object_id': channel.object_id, **body.model_dump()}

class MlChannelRunBody(BaseModel):
    channel_id: int
    as_of: datetime | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=100)

@app.post(api+'/predictions/ml-channel/run')
def ml_channel_run(body: MlChannelRunBody, session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'analyst'))):
    return run_channel_prediction(session, body.channel_id, body.as_of, body.request_id)

@app.post(api+'/predictions/run')
def prediction_run(body: RunBody, session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'analyst'))):
    return {'items': run_predictions(session, provider, body.object_ids, body.as_of, body.horizons_h, request_id=body.request_id)}

@app.get(api+'/predictions')
def predictions(object_id: str | None=None, incident_type: str | None=None, risk: str | None=None, role: str='active', latest: bool=False, limit: int=100, offset: int=0, session=Depends(db, scope='function'), user=Depends(current_user)):
    if role != 'active' and user['role'] not in ('admin', 'analyst'):
        raise HTTPException(403, 'Теневые прогнозы доступны аналитикам')
    query = select(Prediction).where(Prediction.role == role)
    for name, value in [('object_id', object_id), ('incident_type', incident_type), ('risk', risk)]:
        if value:
            query = query.where(getattr(Prediction, name) == value)
    if latest:
        latest_ts = select(func.max(Prediction.as_of)).where(Prediction.role == role).scalar_subquery()
        query = query.where(Prediction.as_of == latest_ts)
    result = page(session, query.order_by(Prediction.as_of.desc(), Prediction.probability.desc()), limit, offset)
    for row in result['items']:
        row['decision'] = next((serialize(d) for d in session.scalars(select(Decision).where(Decision.prediction_id == row['id']).order_by(Decision.ts.desc()))), None)
    return result

@app.get(api+'/predictions/{identity}')
def prediction_detail(identity: str, session=Depends(db, scope='function'), user=Depends(current_user)):
    p = get_or_404(session, Prediction, identity)
    if p.role != 'active' and user['role'] not in ('admin', 'analyst'):
        raise HTTPException(403, 'Теневой прогноз')
    return {**serialize(p), 'decisions': [serialize(d) for d in session.scalars(select(Decision).where(Decision.prediction_id == identity))]}

class DecisionBody(BaseModel):
    action: Literal['dispatch', 'inspect', 'monitor', 'false_alarm']
    reason: str
    comment: str = Field(min_length=3, max_length=2000)
    outcome: Literal['confirmed', 'false', 'monitoring'] = 'monitoring'

@app.post(api+'/predictions/{identity}/decision')
def decision(identity: str, body: DecisionBody, session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'analyst'))):
    p = get_or_404(session, Prediction, identity)
    if p.role != 'active':
        raise ValueError('Решение для теневого прогноза запрещено')
    if body.reason not in config('reasons')['reasons']:
        raise ValueError('Выберите причину из справочника')
    if contains_pii(body.comment):
        raise ValueError('Комментарий содержит возможные персональные данные')
    record = Decision(id=str(uuid4()), prediction_id=identity, username=user['username'], **body.model_dump())
    session.add(record)
    session.flush()
    return serialize(record)

@app.get(api+'/predictions/{identity}/analogs')
def analogs(identity: str, session=Depends(db, scope='function'), user=Depends(current_user)):
    p = get_or_404(session, Prediction, identity)
    prediction_detail(identity, session, user)
    rows = session.scalars(select(Record).where(Record.kind == 'label', Record.ts < p.as_of)).all()
    rows = [r for r in rows if r.data.get('incident_type') == p.incident_type]
    rows.sort(key=lambda r: (r.object_id != p.object_id, abs(utc(r.ts).month-utc(p.as_of).month)))
    return {'items': [serialize(r) for r in rows[:5]], 'method': 'Тот же тип инцидента; приоритет объекта и сезона'}

@app.post(api+'/predictions/what-if')
def what_if(body: dict, session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'analyst'))):
    request = ContextBuilder(session).build(body['object_ids'], now(), what_if={'weather.forecast.precip_mm_delta': float(body.get('precip_mm_delta', 0))})
    return provider.predict(request).model_dump(mode='json')

@app.get(api+'/recommendations')
def recommendations(session=Depends(db, scope='function'), user=Depends(current_user)):
    return page(session, select(Record).where(Record.kind == 'recommendation').order_by(Record.ts.desc()), 1000)

@app.patch(api+'/recommendations/{identity}')
def recommendation_update(identity: str, body: dict, session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'technician'))):
    row = get_or_404(session, Record, identity)
    if row.kind != 'recommendation' or body.get('status') not in ('accepted', 'rejected', 'completed'):
        raise ValueError('Недопустимый статус рекомендации')
    if body['status'] == 'rejected' and not body.get('reason'):
        raise ValueError('Для отклонения нужна причина')
    row.data = {**row.data, 'status': body['status'], 'reason': body.get('reason'), 'updated_by': user['username']}
    return serialize(row)

class WorkNoteBody(BaseModel):
    text: str = Field(min_length=3, max_length=1000)

@app.post(api+'/recommendations/{identity}/notes')
def recommendation_note(identity: str, body: WorkNoteBody, session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'technician'))):
    row = get_or_404(session, Record, identity)
    if row.kind != 'recommendation':
        raise ValueError('Не рекомендация')
    note = body.text.strip()
    if len(note) < 3:
        raise ValueError('Комментарий: от 3 до 1000 символов')
    row.data = {**row.data, 'work_notes': [*row.data.get('work_notes', []), {'author': user['username'], 'ts': now().isoformat(), 'text': note}]}
    return serialize(row)

@app.get(api+'/evaluation/metrics')
def quality(incident_type: str | None=None, model_id: str | None=None, model_version: str | None=None, role: str | None=None, start: datetime | None=None, end: datetime | None=None, session=Depends(db, scope='function'), user=Depends(require('analyst', 'manager'))):
    return evaluate(session, incident_type, model_id, model_version, role, start, end)

@app.get(api+'/evaluation/model-comparison')
def comparison(session=Depends(db, scope='function'), user=Depends(require('analyst', 'manager'))):
    groups = session.execute(select(Prediction.model_id, Prediction.model_version, Prediction.role).distinct()).all()
    return [{'model_id': m, 'version': v, 'role': r, 'metrics': evaluate(session, model_id=m, model_version=v, role=r)} for m, v, r in groups]

@app.post(api+'/evaluation/backtest')
def backtest(body: dict, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    start, end = parse_date(body['start']), parse_date(body['end'])
    step = max(1, int(body.get('step_hours', 24)))
    if end <= start or (end-start).total_seconds()/3600/step > 366:
        raise ValueError('От 1 до 366 временных точек')
    timestamp, count = start, 0
    while timestamp <= end:
        count += len(run_predictions(session, provider, body.get('object_ids'), timestamp, role='backtest', notify=False))
        timestamp += timedelta(hours=step)
    return {'predictions': count, 'metrics': evaluate(session, role='backtest', start=start, end=end)}

@app.post(api+'/evaluation/validate-upload')
def validate_upload(body: dict, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    ingestion = ingest_events(session, body['events'])
    ods(body['labels'], session, user)
    for coverage in body['coverage']:
        get_or_404(session, Object, coverage['object_id'])
        session.merge(Record(id='coverage:'+coverage['object_id'], kind='coverage', object_id=coverage['object_id'], data=coverage))
    result = backtest(body['backtest'], session, user)
    return {'ingestion': ingestion, **result}

@app.get(api+'/ml/status')
def ml_status(user=Depends(current_user)):
    return provider.health()

@app.get(api+'/ml/models')
def ml_models(user=Depends(require('analyst'))):
    return provider.list_models()

@app.post(api+'/ml/train')
def ml_train(body: TrainJob, user=Depends(require('analyst'))):
    return provider.start_training(body.model_dump(mode='json'))

@app.get(api+'/ml/jobs/{identity}')
def ml_job(identity: str, user=Depends(require('analyst'))):
    return provider.get_job(identity)

@app.post(api+'/ml/models/{identity}/activate')
def activate(identity: str, user=Depends(require('analyst'))):
    return provider.activate(identity)

@app.post(api+'/ml/models/{identity}/shadow')
def shadow(identity: str, user=Depends(require('analyst'))):
    return provider.shadow(identity)

@app.get(api+'/settings')
def read_settings(session=Depends(db, scope='function'), user=Depends(current_user)):
    return {**settings(session), 'reasons': config('reasons'), 'ml_mode': provider.mode}

@app.put(api+'/settings')
def save_settings(body: dict, session=Depends(db, scope='function'), user=Depends(require('admin'))):
    allowed = set(config('settings')) | {'ml_mode'}
    if set(body)-allowed:
        raise ValueError('Неизвестные параметры')
    merged = {**settings(session), **body}
    t = merged['risk_thresholds']
    if not 0 <= t['low'] < t['medium'] < t['high'] <= 1 or min(merged['horizons_h']) < 24 or merged['context_hours'] <= 0 or merged['maintenance_days'] <= 0:
        raise ValueError('Недопустимые пороги или интервалы')
    if 'ml_mode' in body:
        if body['ml_mode'] not in ('rules', 'http', 'plugin', 'ensemble', 'shadow'):
            raise ValueError('Неизвестный режим')
        provider.mode = body['ml_mode']
        provider.cache.clear()
    session.merge(Record(id='settings', kind='settings', data=merged))
    return merged

@app.get(api+'/admin/users')
def users(session=Depends(db, scope='function'), user=Depends(require('admin'))):
    return [{'username': u.username, 'role': u.role} for u in session.scalars(select(User))]

@app.get(api+'/admin/audit')
def audit(limit: int=100, offset: int=0, session=Depends(db, scope='function'), user=Depends(require('admin'))):
    return page(session, select(Audit).order_by(Audit.id.desc()), limit, offset)

@app.get(api+'/notification-delivery/status')
def delivery_status(user=Depends(require('admin'))):
    return {'channels': [{'channel': channel, 'state': 'disabled'} for channel in ('telegram', 'email', 'sms')]}

@app.get(api+'/notification-delivery/outbox')
def delivery_outbox(user=Depends(require('admin'))):
    return {'items': [], 'total': 0}

@app.get(api+'/notifications')
def notifications(session=Depends(db, scope='function'), user=Depends(current_user)):
    return page(session, select(Record).where(Record.kind == 'notification').order_by(Record.ts.desc()), 100)

@app.post(api+'/notifications/{identity}/read')
def mark_read(identity: str, session=Depends(db, scope='function'), user=Depends(current_user)):
    row = get_or_404(session, Record, identity)
    if row.kind != 'notification':
        raise HTTPException(404, 'Уведомление не найдено')
    row.data = {**row.data, 'read_by': sorted(set(row.data.get('read_by', [])+[user['username']]))}
    return {'ok': True}

@app.get(api+'/notifications/stream')
async def stream(request: Request, user=Depends(current_user)):
    async def generate():
        seen = set()
        while not await request.is_disconnected():
            if now().timestamp() >= user['exp']:
                return
            with Session() as session:
                rows = session.scalars(select(Record).where(Record.kind == 'notification').order_by(Record.ts.desc()).limit(100)).all()
                for row in reversed(rows):
                    if row.id not in seen:
                        seen.add(row.id)
                        yield 'id: '+row.id+'\ndata: '+json.dumps(serialize(row), ensure_ascii=False)+'\n\n'
            yield ': heartbeat\n\n'
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.get(api+'/analytics/incident-stats')
@app.get(api+'/analytics/seasonality')
def stats(session=Depends(db, scope='function'), user=Depends(current_user)):
    counts = defaultdict(int)
    for r in session.scalars(select(Record).where(Record.kind == 'label')):
        counts[(r.data['incident_type'], utc(r.ts).month)] += 1
    return {'items': [{'incident_type': k[0], 'month': k[1], 'count': v} for k, v in sorted(counts.items())]}

@app.post(api+'/datasets/export')
def dataset_export(session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    from backend.exports import export_dataset
    return export_dataset(session)

@app.get(api+'/datasets/{identity}')
def dataset(identity: str, session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    return serialize(get_or_404(session, Record, identity))

@app.post(api+'/feedback/export')
def feedback(session=Depends(db, scope='function'), user=Depends(require('analyst'))):
    return {'schema_version': '1.0', 'items': [serialize(d) for d in session.scalars(select(Decision))]}

@app.get(api+'/reports/{kind}')
def report(kind: str, format: Literal['pdf', 'xlsx']='xlsx', session=Depends(db, scope='function'), user=Depends(require('analyst', 'manager'))):
    from backend.exports import create_report
    path = create_report(session, kind, format)
    return FileResponse(path, filename=path.name)

@app.post(api+'/recommendations/{identity}/draft-order')
def draft_order(identity: str, format: Literal['json', 'pdf']='json', session=Depends(db, scope='function'), user=Depends(require('dispatcher'))):
    row = get_or_404(session, Record, identity)
    if row.kind != 'recommendation':
        raise ValueError('Не рекомендация')
    data = {'draft': True, 'sent': False, 'object_id': row.object_id, **row.data}
    if format == 'json':
        return data
    from backend.exports import pdf_rows
    path = DATA / f'draft-{uuid4()}.pdf'
    pdf_rows(path, 'Черновик заявки. Не отправлен', [data])
    return FileResponse(path, filename=path.name)

@app.post(api+'/demo/{scenario}')
def demo(scenario: Literal['fire', 'flood'], session=Depends(db, scope='function'), user=Depends(require('dispatcher', 'analyst'))):
    if os.getenv('AUTH_MODE', 'demo') != 'demo':
        raise HTTPException(403, 'Демо отключено')
    from tools.emulator.scenarios import inject_scenario
    identity = inject_scenario(session, scenario)
    return {'items': run_predictions(session, provider, [identity])}

if (ROOT / 'frontend/dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True), name='frontend')
