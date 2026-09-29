"""Надёжный потребитель Redis Streams: ACK только после транзакции."""
import json
import logging
import os
import time
from redis import Redis
from redis.exceptions import ResponseError
from backend.db import Session
from backend.jobs import SCORING_STREAM, score_channels
from backend.prediction_providers.http import ProviderRouter
from backend.services import run_predictions, settings


def work():
    queue = Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    for stream, group in (('predictions', 'workers'), (SCORING_STREAM, 'channel-workers')):
        try:
            queue.xgroup_create(stream, group, id='0', mkstream=True)
        except ResponseError as exc:
            if 'BUSYGROUP' not in str(exc):
                raise
    provider = ProviderRouter()
    consumer = str(os.getpid())
    logging.info('Воркер слушает потоки predictions и %s', SCORING_STREAM)
    while True:
        for stream, group in (('predictions', 'workers'), (SCORING_STREAM, 'channel-workers')):
            claimed = queue.xautoclaim(stream, group, consumer, min_idle_time=60000, start_id='0-0', count=1)[1]
            batches = [(stream, claimed)] if claimed else queue.xreadgroup(group, consumer, {stream: '>'}, count=1, block=1000)
            for name, messages in batches:
                for identity, message in messages:
                    try:
                        payload = json.loads(message['payload'])
                        if stream == SCORING_STREAM:
                            report = score_channels(payload.get('channel_ids', []), payload.get('as_of'), payload.get('reason', 'stream'))
                            logging.info('Задание %s: обсчитано %s, пропущено %s', identity, report['scored'], report['skipped'])
                        else:
                            with Session.begin() as session:
                                provider.mode = settings(session).get('ml_mode', os.getenv('ML_MODE', 'rules'))
                                run_predictions(session, provider, payload.get('object_ids'), request_id='stream:'+identity)
                        queue.xack(name, group, identity)
                    except Exception:
                        logging.exception('Ошибка задания %s', identity)
                        time.sleep(1)

if __name__ == '__main__':
    work()
