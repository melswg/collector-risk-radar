"""Надёжный потребитель Redis Streams: ACK только после транзакции."""
import json
import logging
import os
import time
from redis import Redis
from redis.exceptions import ResponseError
from backend.db import Session
from backend.prediction_providers.http import ProviderRouter
from backend.services import run_predictions, settings


def work():
    queue = Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    try:
        queue.xgroup_create('predictions', 'workers', id='0', mkstream=True)
    except ResponseError as exc:
        if 'BUSYGROUP' not in str(exc):
            raise
    provider = ProviderRouter()
    consumer = str(os.getpid())
    while True:
        claimed = queue.xautoclaim('predictions', 'workers', consumer, min_idle_time=60000, start_id='0-0', count=1)[1]
        batches = [('predictions', claimed)] if claimed else queue.xreadgroup('workers', consumer, {'predictions': '>'}, count=1, block=5000)
        for stream, messages in batches:
            for identity, message in messages:
                try:
                    payload = json.loads(message['payload'])
                    with Session.begin() as session:
                        provider.mode = settings(session).get('ml_mode', os.getenv('ML_MODE', 'rules'))
                        run_predictions(session, provider, payload.get('object_ids'), request_id='stream:'+identity)
                    queue.xack(stream, 'workers', identity)
                except Exception:
                    logging.exception('Ошибка задания %s', identity)
                    time.sleep(1)

if __name__ == '__main__':
    work()
