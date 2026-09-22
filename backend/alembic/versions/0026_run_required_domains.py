"""Persist explicit Four Cs requirements on research runs.

Revision ID: 0026_run_required_domains
Revises: 0025_revision_report_document
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_run_required_domains"
down_revision = "0025_revision_report_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("required_domains", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_runs", "required_domains")
