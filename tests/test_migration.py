import importlib
from pathlib import Path
from types import SimpleNamespace
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_initial_migration_loads_backend_schema(monkeypatch):
    migration = importlib.import_module('backend.migrations.versions.0001_initial')
    statements = []
    bind = SimpleNamespace(dialect=SimpleNamespace(name='postgresql'), execute=statements.append)
    monkeypatch.setattr(migration.op, 'get_bind', lambda: bind)
    monkeypatch.setattr(migration.Base.metadata, 'create_all', lambda connection: None)

    migration.upgrade()

    assert len(statements) == 1
    assert str(statements[0]) == Path('backend/schema.sql').read_text()


def test_text_value_migration_upgrades_existing_sqlite(monkeypatch):
    migration = importlib.import_module('backend.migrations.versions.0002_text_sensor_values')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE events (id TEXT PRIMARY KEY, value FLOAT NOT NULL)'))
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert next(c for c in inspect(connection).get_columns('events') if c['name'] == 'value')['nullable']
        connection.execute(text("INSERT INTO events (id, value) VALUES ('text-state', NULL)"))
        with pytest.raises(ValueError, match='текстовые события'):
            migration.downgrade()


def test_unlocated_objects_migration_upgrades_existing_sqlite(monkeypatch):
    migration = importlib.import_module('backend.migrations.versions.0003_unlocated_objects')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE objects (id TEXT PRIMARY KEY, lat FLOAT NOT NULL, lon FLOAT NOT NULL)'))
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        columns = {c['name']: c for c in inspect(connection).get_columns('objects')}
        assert columns['lat']['nullable'] and columns['lon']['nullable']
        connection.execute(text("INSERT INTO objects (id, lat, lon) VALUES ('unknown', NULL, NULL)"))
        with pytest.raises(ValueError, match='без координат'):
            migration.downgrade()
