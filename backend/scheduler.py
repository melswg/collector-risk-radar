"""Планировщик помещает работу в Redis Streams каждые 5 минут."""
import json
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from redis import Redis
from backend.db import Session
from backend.services import settings


def enqueue():
    queue = Redis.from_url(os.environ['REDIS_URL'])
    queue.xadd('predictions', {'payload': json.dumps({'reason': 'scheduled'})}, maxlen=10000)

if __name__ == '__main__':
    with Session() as session:
        interval = settings(session)['schedule_seconds']
    scheduler = BlockingScheduler(timezone='UTC')
    scheduler.add_job(enqueue, 'interval', seconds=interval, max_instances=1)
    scheduler.start()
