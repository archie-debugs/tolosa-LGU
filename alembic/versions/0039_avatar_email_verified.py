"""Profile pictures, and when a user verified their email with Google."""

from alembic import op
import sqlalchemy as sa


revision = "0039_avatar_email_verified"
down_revision = "0038_employee_base_permissions"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "email_verified_at" not in columns:
        op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    if "avatar" not in columns:
        op.add_column("users", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("users", "avatar")
    op.drop_column("users", "email_verified_at")
