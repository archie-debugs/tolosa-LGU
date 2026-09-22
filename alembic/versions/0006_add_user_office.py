"""add optional office assignment to users"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_user_office"
down_revision = "0005_add_reference_definition_activity"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "office_id" not in columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("office_id", sa.Integer(), nullable=True))
            batch_op.create_index("ix_users_office_id", ["office_id"], unique=False)
            batch_op.create_foreign_key("fk_users_office_id_offices", "offices", ["office_id"], ["id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "office_id" in columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_constraint("fk_users_office_id_offices", type_="foreignkey")
            batch_op.drop_index("ix_users_office_id")
            batch_op.drop_column("office_id")