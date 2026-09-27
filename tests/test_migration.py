import importlib
from pathlib import Path
from types import SimpleNamespace


def test_initial_migration_loads_backend_schema(monkeypatch):
    migration = importlib.import_module('backend.migrations.versions.0001_initial')
    statements = []
    bind = SimpleNamespace(dialect=SimpleNamespace(name='postgresql'), execute=statements.append)
    monkeypatch.setattr(migration.op, 'get_bind', lambda: bind)
    monkeypatch.setattr(migration.Base.metadata, 'create_all', lambda connection: None)

    migration.upgrade()

    assert len(statements) == 1
    assert str(statements[0]) == Path('backend/schema.sql').read_text()
