"""Script to apply database migrations."""
from alembic.config import Config
from alembic import command

alembic_cfg = Config('alembic.ini')
command.upgrade(alembic_cfg, 'head')
print('Migrations applied successfully!')