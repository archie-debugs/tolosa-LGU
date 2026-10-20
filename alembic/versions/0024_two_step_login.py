"""Two-step login: authenticator secret and recovery codes on users"""

from alembic import op
import sqlalchemy as sa


revision = "0024_two_step_login"
down_revision = "0023_notifications_seen_at"
branch_labels = None
depends_on = None

COLUMNS = [
    ("totp_secret", sa.String()),
    ("totp_pending_secret", sa.String()),
    ("totp_enabled_at", sa.DateTime(timezone=True)),
    ("totp_last_step", sa.Integer()),
    ("totp_recovery_codes", sa.Text()),
]


def upgrade():
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    for name, kind in COLUMNS:
        if name not in existing:
            op.add_column("users", sa.Column(name, kind, nullable=True))


def downgrade():
    for name, _ in reversed(COLUMNS):
        op.drop_column("users", name)
