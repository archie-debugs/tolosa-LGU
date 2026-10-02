"""add office management metadata"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0012_office_management"
down_revision = "0011_tracking_alias_seq"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("offices", sa.Column("office_code", sa.String(length=32), nullable=True))
    op.add_column(
        "offices",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "offices",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "offices",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    offices = bind.execute(sa.text("SELECT id, office_code, created_at, updated_at FROM offices")).all()
    for office in offices:
        bind.execute(
            sa.text("""
                UPDATE offices
                SET office_code = :office_code, created_at = :created_at, updated_at = :updated_at
                WHERE id = :office_id
            """),
            {
                "office_code": office.office_code or f"OFF-{int(office.id):03d}",
                "created_at": office.created_at or now,
                "updated_at": office.updated_at or now,
                "office_id": office.id,
            },
        )

    with op.batch_alter_table("offices") as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.create_index("ix_offices_office_code", "offices", ["office_code"], unique=True)
    op.create_index("ix_offices_is_active", "offices", ["is_active"], unique=False)


def downgrade():
    op.drop_index("ix_offices_is_active", table_name="offices")
    op.drop_index("ix_offices_office_code", table_name="offices")
    op.drop_column("offices", "updated_at")
    op.drop_column("offices", "created_at")
    op.drop_column("offices", "is_active")
    op.drop_column("offices", "office_code")