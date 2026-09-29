"""Фоновые расчёты каналов: очередь Redis на стенде, поток в процессе на локальной машине.

Локальный запуск идёт без Redis, поэтому задания выполняются сразу в фоне запроса.
На стенде с Redis тот же код забирает воркер из потока `channel-scoring`.
"""

import json
import logging
import os
import threading
import time
from datetime import timedelta

from sqlalchemy import select

from backend.db import Event, Session
from backend.ml_channel import automatic_request_id, feature_hour_for, run_channel_prediction

SCORING_STREAM = 'channel-scoring'
MAX_CHANNELS_PER_RUN = 200
log = logging.getLogger(__name__)


def redis_url() -> str | None:
    return os.getenv('REDIS_URL') or None


def scoring_enabled() -> bool:
    """Оператор может выключить автоматический расчёт, не трогая код."""
    return os.getenv('ML_SCORING_ENABLED', '1') != '0'


def candidate_channels(session, as_of=None, limit: int = 250) -> list[int]:
    """Channels that reported during the hour the model would score."""
    hour = feature_hour_for(as_of)
    rows = session.scalars(
        select(Event.channel_id)
        .where(Event.ts >= hour, Event.ts < hour + timedelta(hours=1))
        .distinct()
        .limit(limit)
    ).all()
    return list(rows)


def score_channels(channel_ids, as_of=None, trigger: str = 'ingest') -> dict:
    """Score the given channels, one transaction per channel, skipping what cannot be scored."""
    started = time.monotonic()
    unique = [int(channel_id) for channel_id in dict.fromkeys(channel_ids)][:MAX_CHANNELS_PER_RUN]
    report = {'requested': len(unique), 'scored': 0, 'skipped': 0, 'skipped_reasons': {}, 'predictions': []}
    for channel_id in unique:
        try:
            with Session.begin() as session:
                prediction = run_channel_prediction(
                    session, channel_id, as_of, automatic_request_id(channel_id, as_of),
                    trigger=trigger, latency_ms=round((time.monotonic() - started) * 1000, 3),
                )
            report['scored'] += 1
            report['predictions'].append({'channel_id': channel_id, 'prediction_id': prediction['id']})
        except Exception as exc:  # канал без паспорта, пустой час, отказ модели
            reason = str(exc)
            report['skipped'] += 1
            report['skipped_reasons'][reason] = report['skipped_reasons'].get(reason, 0) + 1
            log.info('Канал %s не обсчитан: %s', channel_id, reason)
    report['duration_ms'] = round((time.monotonic() - started) * 1000, 3)
    return report


def start_local_scheduler(interval_seconds: int = 300):
    """На локальной машине без Redis поток сам досчитывает каналы по завершённому часу."""
    if os.getenv('ML_LOCAL_SCHEDULER', '1') == '0':
        return None
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

    def loop():
        while True:
            time.sleep(interval_seconds)
            try:
                with Session() as session:
                    channels = candidate_channels(session)
                if channels:
                    report = score_channels(channels, None, 'schedule')
                    log.info('Плановый расчёт каналов: обсчитано %s, пропущено %s', report['scored'], report['skipped'])
            except Exception:
                log.exception('Плановый расчёт каналов не выполнен')

    thread = threading.Thread(target=loop, name='channel-scheduler', daemon=True)
    thread.start()
    return thread


def enqueue_channel_scoring(channel_ids, reason: str = 'ingest', synchronous: bool | None = None) -> dict:
    """Send the channels to the queue when Redis is configured, otherwise score in a thread here."""
    unique = [int(channel_id) for channel_id in dict.fromkeys(channel_ids)]
    if not unique:
        return {'mode': 'skipped', 'channels': 0}
    if not scoring_enabled():
        return {'mode': 'disabled', 'channels': len(unique)}
    if synchronous is None:
        synchronous = os.getenv('ML_SCORING_SYNC') == '1'
    url = redis_url()
    if url and not synchronous:
        from redis import Redis
        queue = Redis.from_url(url, decode_responses=True)
        queue.xadd(SCORING_STREAM, {'payload': json.dumps({'channel_ids': unique, 'reason': reason})}, maxlen=10000)
        return {'mode': 'stream', 'channels': len(unique)}
    if synchronous:
        return {'mode': 'inline', 'channels': len(unique), **score_channels(unique, None, reason)}
    threading.Thread(target=score_channels, args=(unique, None, reason), name='channel-scoring', daemon=True).start()
    return {'mode': 'background', 'channels': len(unique)}
