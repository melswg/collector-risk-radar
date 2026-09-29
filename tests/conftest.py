import os
import tempfile
from pathlib import Path
import pytest

TEST_DIR=Path(tempfile.mkdtemp(prefix='moscollector-tests-'))
os.environ.update(DATABASE_URL='sqlite:///'+str(TEST_DIR/'test.db'),DATA_DIR=str(TEST_DIR),AUTH_MODE='demo',DEMO_PASSWORD='test-password-2026-long',JWT_SECRET='test-only-secret-with-at-least-32-characters',ML_SERVICE_TOKEN='test-service-token',ML_STORE=str(TEST_DIR/'ml'),COOKIE_SECURE='false',ML_SCORING_ENABLED='0',ML_LOCAL_SCHEDULER='0')

@pytest.fixture
def live_scoring(monkeypatch):
    """Включает синхронный автоматический расчёт каналов для конкретного теста."""
    monkeypatch.setenv('ML_SCORING_ENABLED', '1')
    monkeypatch.setenv('ML_SCORING_SYNC', '1')

def pytest_addoption(parser):
    parser.addoption('--ml-url',action='store',default=None)

@pytest.fixture
def session():
    from backend.db import Base,engine,Session
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session.begin() as s:
        yield s

def populate(s):
    from backend.db import Object,Channel
    from backend.ingestion import TYPES
    from backend.auth import seed_users
    for i in [1,2]:
        s.add(Object(id=f'obj-{i:06d}',name=f'Коллектор {i}',tag=f'МК-{i}.1',lat=55.7,lon=37.6,meta={'commissioned_year':1980,'criticality':3}))
        s.flush()
        for t,c in TYPES.items():
            s.add(Channel(id=(i-1)*100+t,object_id=f'obj-{i:06d}',type_id=t,type_code=c))
    seed_users(s);s.flush()

@pytest.fixture
def populated(session):
    populate(session)
    return session

@pytest.fixture
def client():
    from backend.db import Base,engine,Session
    from backend.api import app,rate_buckets,provider
    from fastapi.testclient import TestClient
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    rate_buckets.clear();provider.mode='rules';provider.cache.clear()
    with Session.begin() as s:
        populate(s)
    with TestClient(app) as c:
        assert c.post('/api/v1/auth/login',json={'username':'admin','password':os.environ['DEMO_PASSWORD']}).status_code==200
        yield c
