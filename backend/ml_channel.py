"""Channel-level ML forecast from stored passport and causal sensor events."""

import hashlib
from datetime import timedelta
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from backend.db import Channel, Event, Prediction, Record, now, serialize, utc
from backend.ingestion import source_alarm


MODEL_DIR = Path(__file__).resolve().parents[1] / 'ml-заново' / 'models'
MODEL_PATH = MODEL_DIR / 'incident_24h.cbm'


@lru_cache(maxsize=1)
def predictor():
    model = import_module('ml-заново.inference')
    return model.AlarmPredictor(
        MODEL_PATH,
        MODEL_DIR / 'new_alarm_channel_isotonic.joblib',
    )


def run_channel_prediction(session, channel_id: int, as_of, request_id: str | None = None):
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise ValueError('Неизвестный канал')
    passport = session.get(Record, f'ml-passport:{channel_id}')
    if passport is None:
        raise ValueError('Для канала не зарегистрирован ML-паспорт')
    timestamp = utc(as_of or now())
    identity = f'ml-channel:{request_id}' if request_id else str(uuid4())
    previous = session.scalar(select(Prediction).where(Prediction.request_id == identity))
    if previous:
        if previous.extra.get('channel_id') != channel_id or utc(previous.as_of) != timestamp:
            raise ValueError('request_id уже использован для другого расчёта')
        return serialize(previous)
    rows = session.scalars(select(Event).where(Event.channel_id == channel_id, Event.ts < timestamp).order_by(Event.ts)).all()
    history = []
    for event in rows:
        raw_alarm = event.raw.get('тревожное') if isinstance(event.raw, dict) else None
        history.append({
            'timestamp': utc(event.ts).isoformat(),
            'alarm': source_alarm(raw_alarm) if raw_alarm is not None else event.severity == 'warning',
            'value': event.raw.get('значение_датчика', event.value) if isinstance(event.raw, dict) else event.value,
        })
    feature_builder = import_module('ml-заново.feature_builder')
    features = feature_builder.build_model_features({
        'as_of': timestamp.isoformat(), 'channel': passport.data, 'history': history,
    })
    if not features['n_events']:
        raise ValueError('В текущем часе нет событий канала; ML-строка не формируется')
    result = predictor().predict(features)
    if not result['probability_calibrated']:
        raise RuntimeError('Калибратор вероятности не загружен')
    prediction = Prediction(
        id=str(uuid4()), request_id=identity, object_id=channel.object_id,
        incident_type='new_alarm_24h', horizon_h=24, probability=result['probability'],
        risk='unrated', as_of=timestamp, valid_until=timestamp + timedelta(hours=24),
        provider='ml', model_id='incident_24h',
        model_version=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:12], model_kind='ml',
        role='active', data_sufficiency='sufficient',
        explanation={'target': result['target'], 'predicted_type': result['predicted_type']},
        extra={
            'channel_id': channel_id, 'synthetic': bool(passport.data.get('synthetic')),
            'raw_probability': result['raw_probability'], 'probability_calibrated': True,
            'feature_count': len(features), 'threshold': None,
        },
    )
    session.add(prediction)
    session.flush()
    return serialize(prediction)
