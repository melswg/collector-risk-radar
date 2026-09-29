"""Add Telegram account links and notification delivery log.

Uses Base.metadata.create_all(checkfirst=True) like 0001_initial, because on a fresh
database 0001 already bootstraps every model currently defined in backend/db.py
(including these two) — this revision only fills the gap on a database that was
migrated to 0002 before these models existed.
"""
from alembic import op
from backend.db import Base

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

TABLES = ['telegram_links', 'notification_deliveries']


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=[Base.metadata.tables[name] for name in TABLES], checkfirst=True)


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind, tables=[Base.metadata.tables[name] for name in reversed(TABLES)], checkfirst=True)
