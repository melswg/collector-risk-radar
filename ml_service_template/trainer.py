"""ТОЧКА РАСШИРЕНИЯ ML: реальное обучение реализует ML-разработчик."""
import logging


def train(job):
    logging.warning('STUB: обучение не выполнялось')
    return {'id': 'stub', 'version': job.job_id, 'kind': 'stub', 'metrics': {}, 'model_card': 'STUB: не обученная модель'}
