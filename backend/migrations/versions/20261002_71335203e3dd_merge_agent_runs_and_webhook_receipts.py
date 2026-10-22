"""merge agent runs and webhook receipts

Revision ID: 71335203e3dd
Revises: 0a12fbc7e3b9, 82447f99cb7e
Create Date: 2026-10-02 08:28:13.388843
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db


revision: str = "71335203e3dd"
down_revision: str | None = ("0a12fbc7e3b9", "82447f99cb7e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
