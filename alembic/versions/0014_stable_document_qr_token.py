"""add stable document QR identity tokens"""

from alembic import op
import sqlalchemy as sa
import secrets


revision = "0014_stable_document_qr_token"
down_revision = "0012_office_management"
branch_labels = None
depends_on = None


def _generate_unique_token(bind) -> str:
    while True:
        token = secrets.token_urlsafe(32)
        existing = bind.execute(sa.text("SELECT id FROM documents WHERE qr_token = :token"), {"token": token}).fetchone()
        if existing is None:
            return token


def upgrade():
    bind = op.get_bind()
    columns = [column["name"] for column in sa.inspect(bind).get_columns("documents")]

    if "qr_token" not in columns:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("documents") as batch_op:
                batch_op.add_column(sa.Column("qr_token", sa.String(length=64), nullable=True))
        else:
            op.add_column("documents", sa.Column("qr_token", sa.String(length=64), nullable=True))

    rows = bind.execute(sa.text("SELECT id FROM documents WHERE qr_token IS NULL OR qr_token = ''")).fetchall()
    for (document_id,) in rows:
        token = _generate_unique_token(bind)
        bind.execute(sa.text("UPDATE documents SET qr_token = :token WHERE id = :id"), {"token": token, "id": document_id})

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column("qr_token", existing_type=sa.String(length=64), nullable=False)
            batch_op.create_index(batch_op.f("ix_documents_qr_token"), ["qr_token"], unique=True)
    else:
        op.alter_column("documents", "qr_token", existing_type=sa.String(length=64), nullable=False)
        op.create_index("ix_documents_qr_token", "documents", ["qr_token"], unique=True)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("documents") as batch_op:
            batch_op.drop_index(batch_op.f("ix_documents_qr_token"))
            batch_op.drop_column("qr_token")
    else:
        op.drop_index("ix_documents_qr_token", table_name="documents")
        op.drop_column("documents", "qr_token")
