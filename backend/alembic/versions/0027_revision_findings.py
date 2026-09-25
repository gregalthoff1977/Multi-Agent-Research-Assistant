"""Persist assessed findings on immutable report revisions.

Revision ID: 0027_revision_findings
Revises: 0026_run_required_domains
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_revision_findings"
down_revision = "0026_run_required_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("revisions", sa.Column("findings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("revisions", "findings")
