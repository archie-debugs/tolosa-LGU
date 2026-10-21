"""Handoffs can be cancelled by the sender or returned by the receiver before receipt"""

from alembic import op
import sqlalchemy as sa


revision = "0025_handoff_cancel_return"
down_revision = "0024_two_step_login"
branch_labels = None
depends_on = None

TABLE = "document_handoffs"
STATUS_CHECK = "ck_document_handoffs_status"
OLD_STATUSES = "status IN ('Pending Receipt', 'Received')"
NEW_STATUSES = "status IN ('Pending Receipt', 'Received', 'Cancelled', 'Returned')"


def _replace_status_check(bind, condition):
    if bind.dialect.name == "sqlite":
        # SQLite cannot alter a constraint; batch mode copies the table.
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(STATUS_CHECK, type_="check")
            batch_op.create_check_constraint(STATUS_CHECK, condition)
    else:
        op.drop_constraint(STATUS_CHECK, TABLE, type_="check")
        op.create_check_constraint(STATUS_CHECK, TABLE, condition)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns(TABLE)}
    if "closed_at" not in existing:
        op.add_column(TABLE, sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    if "closed_by_user_id" not in existing:
        op.add_column(TABLE, sa.Column("closed_by_user_id", sa.Integer(), nullable=True))
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_document_handoffs_closed_by_user_id", TABLE, "users", ["closed_by_user_id"], ["id"], ondelete="SET NULL",
            )
    if "close_reason" not in existing:
        op.add_column(TABLE, sa.Column("close_reason", sa.Text(), nullable=True))

    checks = {check["name"]: check["sqltext"] for check in sa.inspect(bind).get_check_constraints(TABLE)}
    if STATUS_CHECK in checks and "Returned" not in checks[STATUS_CHECK]:
        _replace_status_check(bind, NEW_STATUSES)


def downgrade():
    bind = op.get_bind()
    closed = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE status IN ('Cancelled', 'Returned')")).scalar()
    if closed:
        # The old statuses cannot describe these rows; relabelling them would falsify the history.
        raise RuntimeError(f"{closed} cancelled or returned handoff(s) exist; remove them before downgrading below 0025.")
    _replace_status_check(bind, OLD_STATUSES)
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_document_handoffs_closed_by_user_id", TABLE, type_="foreignkey")
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_column("close_reason")
        batch_op.drop_column("closed_by_user_id")
        batch_op.drop_column("closed_at")
