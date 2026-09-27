"""Allow sensor states that have no numeric measurement."""
from alembic import op
from sqlalchemy import Float, text

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('events') as batch:
        batch.alter_column('value', existing_type=Float(), nullable=True)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('ALTER TABLE archive.events ALTER COLUMN value DROP NOT NULL')


def downgrade():
    bind = op.get_bind()
    if bind.scalar(text('SELECT count(*) FROM events WHERE value IS NULL')):
        raise ValueError('Есть текстовые события; возврат к обязательному числовому значению невозможен')
    if bind.dialect.name == 'postgresql':
        if bind.scalar(text('SELECT count(*) FROM archive.events WHERE value IS NULL')):
            raise ValueError('В архиве есть текстовые события; возврат невозможен')
        op.execute('ALTER TABLE archive.events ALTER COLUMN value SET NOT NULL')
    with op.batch_alter_table('events') as batch:
        batch.alter_column('value', existing_type=Float(), nullable=False)
