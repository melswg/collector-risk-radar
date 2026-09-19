"""Сценарии приложения используют только контракт провайдера."""
import hashlib
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from backend.analytics import is_expected, label_window, metrics
from backend.context import ContextBuilder
from backend.db import Decision, Object, Prediction, Record, now, serialize, utc
from backend.settings import config


def settings(session):
    row = session.get(Record, 'settings')
    return {**config('settings'), **(row.data if row else {})}


def risk_level(probability, thresholds):
    if probability is None:
        return 'insufficient'
    return 'high' if probability >= thresholds['high'] else 'medium' if probability >= thresholds['medium'] else 'low' if probability >= thresholds['low'] else 'normal'


def recommendation(obj, prediction, context, cfg, as_of):
    health = [c.health for c in context.channels]
    unhealthy = sum(h.get('status') != 'ok' for h in health)/max(len(health), 1)
    age = max(0, as_of.year-int(obj.meta.get('commissioned_year', as_of.year)))
    last = obj.meta.get('last_service_at')
    last_date = utc(__import__('datetime').datetime.fromisoformat(last)) if last else as_of-timedelta(days=cfg['maintenance_days'])
    due = (as_of-last_date).days/cfg['maintenance_days']
    priority = min(100, round(55*(prediction.probability or 0)+20*unhealthy+10*min(age/50, 1)+10*min(due, 2)+obj.meta.get('criticality', 1)*cfg['criticality_weight']*10))
    start = as_of+timedelta(hours=2)
    for _ in range(30*24):
        conflict = any(utc(__import__('datetime').datetime.fromisoformat(w['from'])) < start+timedelta(hours=2) and utc(__import__('datetime').datetime.fromisoformat(w['to'])) > start and w.get('status') in ('approved', 'in_progress') for w in context.planned_works)
        rain = any(float(w.get('precip_mm', 0)) > 5 and abs((utc(__import__('datetime').datetime.fromisoformat(w['ts']))-start).total_seconds()) < 7200 for w in context.weather.get('forecast', []))
        if not conflict and not rain:
            break
        start += timedelta(hours=1)
    action = {'fire': 'Проверить пожарную систему и вентиляцию', 'flood': 'Проверить насосы, питание и водоотвод', 'sensor_failure': 'Диагностика, калибровка или замена датчика', 'intrusion_false_alarm': 'Проверить датчик и сопутствующие сигналы'}[prediction.incident_type]
    return dict(prediction_id=prediction.id, priority=priority, action=action, status='new', window_from=start.isoformat(), window_to=(start+timedelta(hours=2)).isoformat(), rationale={'probability': prediction.probability, 'unhealthy_fraction': unhealthy, 'age_years': age, 'maintenance_due_ratio': due, 'open_orders': context.maintenance.get('open_orders', 0)}, schedule_comparison='Провести раньше' if priority >= 60 else 'Сохранить плановый срок', regulatory_note=cfg['maintenance_note'])


def run_predictions(session, provider, object_ids=None, as_of=None, horizons=None, role='active', request_id=None, notify=True):
    timestamp = utc(as_of or now())
    cfg = settings(session)
    if horizons and min(horizons) < 24:
        raise ValueError('Для диспетчерского прогноза горизонт не менее 24 часов')
    ids = object_ids or list(session.scalars(select(Object.id)).all())
    output = []
    for offset in range(0, len(ids), 50):
        batch_id = (request_id + f':{offset}') if request_id else str(uuid4())
        existing = session.scalars(select(Prediction).where(Prediction.request_id == batch_id)).all()
        if existing:
            output.extend(serialize(p) for p in existing)
            continue
        request = ContextBuilder(session).build(ids[offset:offset+50], timestamp, horizons, request_id=batch_id)
        response = provider.predict(request)
        responses = [(role, response)]
        if role == 'active' and hasattr(provider, 'predict_shadow'):
            shadow = provider.predict_shadow(request)
            if shadow:
                responses.append(('shadow', shadow))
        for prediction_role, result in responses:
            for item in result.predictions:
                context = next(o for o in request.objects if o.object_id == item.object_id)
                pred = Prediction(id=str(uuid4()), request_id=request.request_id, object_id=item.object_id, incident_type=item.incident_type, horizon_h=item.horizon_h, probability=item.probability, risk=risk_level(item.probability, cfg['risk_thresholds']), as_of=timestamp, valid_until=timestamp+timedelta(hours=item.horizon_h), provider=result.model.kind, model_id=result.model.id, model_version=result.model.version, model_kind=result.model.kind, role=prediction_role, data_sufficiency=item.data_sufficiency, explanation=item.explanation, extra={'warnings': item.warnings, 'alarm_ref': item.alarm_ref, 'analogs': item.analogs, 'expected': is_expected(timestamp, context.planned_works, cfg['planned_work_tolerance_minutes'])})
                session.add(pred)
                session.flush()
                output.append(serialize(pred))
                if prediction_role != 'active' or not notify:
                    continue
                if pred.probability is not None and pred.probability >= cfg['notification_threshold'] and pred.incident_type != 'intrusion_false_alarm' and not pred.extra['expected']:
                    key = hashlib.sha256(f'{pred.object_id}:{pred.incident_type}:{pred.risk}'.encode()).hexdigest()[:20]
                    last = session.get(Record, 'dedup:'+key)
                    if not last or timestamp-utc(last.ts) >= timedelta(minutes=cfg['notification_cooldown_minutes']):
                        session.merge(Record(id='dedup:'+key, kind='dedup', object_id=pred.object_id, ts=timestamp, available_at=timestamp, data={'risk': pred.risk}))
                        session.add(Record(id=str(uuid4()), kind='notification', object_id=pred.object_id, ts=timestamp, data={'prediction_id': pred.id, 'incident_type': pred.incident_type, 'risk': pred.risk, 'probability': pred.probability, 'read_by': []}))
                if pred.probability is not None and pred.probability >= cfg['risk_thresholds']['medium']:
                    obj = session.get(Object, pred.object_id)
                    rec_id = 'rec:'+pred.object_id+':'+pred.incident_type
                    current = session.get(Record, rec_id)
                    if current is None or current.data.get('status') == 'new':
                        session.merge(Record(id=rec_id, kind='recommendation', object_id=pred.object_id, ts=timestamp, data=recommendation(obj, pred, context, cfg, timestamp)))
    return output


def evaluate(session, incident_type=None, model_id=None, model_version=None, role=None, start=None, end=None, threshold=0.5):
    query = select(Prediction).where(Prediction.valid_until <= now())
    for attr, val in [('incident_type', incident_type), ('model_id', model_id), ('model_version', model_version), ('role', role)]:
        if val:
            query = query.where(getattr(Prediction, attr) == val)
    if start:
        query = query.where(Prediction.as_of >= start)
    if end:
        query = query.where(Prediction.as_of <= end)
    predictions = session.scalars(query.order_by(Prediction.as_of)).all()
    truth = session.scalars(select(Record).where(Record.kind == 'label')).all()
    coverage = session.scalars(select(Record).where(Record.kind == 'coverage')).all()
    labels, probabilities, lead_times, pairs = [], [], [], []
    object_days = set()
    seen = set()
    for p in predictions:
        key = (p.object_id, p.incident_type, p.horizon_h, utc(p.as_of), p.model_id, p.model_version, p.role)
        if key in seen or p.probability is None:
            continue
        seen.add(key)
        relevant = [r for r in truth if r.object_id == p.object_id and r.data['incident_type'] == p.incident_type]
        covered = [c for c in coverage if c.object_id == p.object_id and utc(__import__('datetime').datetime.fromisoformat(c.data['from'])) <= utc(p.as_of) and utc(__import__('datetime').datetime.fromisoformat(c.data['to'])) >= utc(p.valid_until)]
        if not covered:
            continue
        if p.incident_type == 'intrusion_false_alarm':
            alarm = p.extra.get('alarm_ref')
            matched = [r for r in relevant if r.data.get('alarm_ref') == alarm and alarm]
            if not matched:
                continue
            label = int(matched[-1].data.get('is_false', True))
        else:
            label = label_window(p.as_of, p.horizon_h, [r.ts for r in relevant], p.valid_until)
        labels.append(label)
        probabilities.append(p.probability)
        object_days.add((p.object_id, utc(p.as_of).date()))
        if label and p.probability >= threshold:
            future = [r for r in relevant if utc(p.as_of) < utc(r.ts) <= utc(p.valid_until)]
            if future:
                lead_times.append(min((utc(r.ts)-utc(p.as_of)).total_seconds()/3600 for r in future))
        pairs.append(dict(as_of=utc(p.as_of).isoformat(), object_id=p.object_id, probability=p.probability, label=label, model=p.model_id, role=p.role))
    result = metrics(labels, probabilities, threshold, len(object_days), lead_times)
    result.update(synthetic=all(c.data.get('synthetic', False) for c in coverage) if coverage else None, excluded=len(predictions)-len(labels), series=pairs, note='Метрики по завершённым горизонтам с подтверждённым покрытием. На синтетике не доказывают реальную точность.')
    return result
