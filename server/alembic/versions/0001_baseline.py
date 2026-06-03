"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op

from app.ai.command_models import CommandProposalRecord, CommandProposalStepRecord  # noqa: F401
from app.ai.model_config_models import AIModelProviderConfig  # noqa: F401
from app.tianshu_runtime.models import RuntimeEvent, RuntimeState  # noqa: F401
from app.auth.models import User  # noqa: F401
from app.db.base import Base
from app.scenarios.models import AarRecord, Scenario, TrainingScoreRecord  # noqa: F401
from app.unit_assets.models import UnitAsset  # noqa: F401

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
