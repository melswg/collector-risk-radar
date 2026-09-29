"""Keep customer objects whose coordinates were not supplied."""

from alembic import op
from sqlalchemy import Float, text

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('objects') as batch:
        batch.alter_column('lat', existing_type=Float(), nullable=True)
        batch.alter_column('lon', existing_type=Float(), nullable=True)


def downgrade():
    bind = op.get_bind()
    if bind.scalar(text('SELECT count(*) FROM objects WHERE lat IS NULL OR lon IS NULL')):
        raise ValueError('Есть объекты без координат; возврат к обязательной геопозиции невозможен')
    with op.batch_alter_table('objects') as batch:
        batch.alter_column('lat', existing_type=Float(), nullable=False)
        batch.alter_column('lon', existing_type=Float(), nullable=False)
