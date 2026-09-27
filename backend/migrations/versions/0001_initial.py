"""Базовые таблицы, архивные партиции, аналитические витрины и роль чтения."""
from alembic import op
from sqlalchemy import text
from backend.db import Base
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name != 'postgresql':
        return
    from pathlib import Path
    sql = (Path(__file__).parents[2]/'schema.sql').read_text()
    bind.execute(text(sql))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        bind.execute(text('DROP SCHEMA IF EXISTS ml CASCADE; DROP SCHEMA IF EXISTS archive CASCADE;'))
    Base.metadata.drop_all(bind)
