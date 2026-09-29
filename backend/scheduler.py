"""Планировщик помещает работу в Redis Streams: расчёт объектов и досчёт каналов по часу."""
import json
import logging
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from redis import Redis
from backend.db import Session
from backend.jobs import candidate_channels, enqueue_channel_scoring
from backend.services import settings


def enqueue():
    queue = Redis.from_url(os.environ['REDIS_URL'])
    queue.xadd('predictions', {'payload': json.dumps({'reason': 'scheduled'})}, maxlen=10000)


def enqueue_channels():
    """Каналы, которые прислали события в расчётном часе, но ещё не обсчитаны."""
    with Session() as session:
        channels = candidate_channels(session)
    if not channels:
        logging.info('Плановый расчёт каналов: новых каналов нет')
        return
    logging.info('Плановый расчёт каналов: %s', enqueue_channel_scoring(channels, reason='schedule'))

if __name__ == '__main__':
    with Session() as session:
        interval = settings(session)['schedule_seconds']
    scheduler = BlockingScheduler(timezone='UTC')
    scheduler.add_job(enqueue, 'interval', seconds=interval, max_instances=1)
    scheduler.add_job(enqueue_channels, 'interval', seconds=interval, max_instances=1)
    scheduler.start()
