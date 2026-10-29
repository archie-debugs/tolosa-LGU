"""One tracking-number sequence per document type: ORD-, RES- and LTR- replace the shared DOC- one

Existing documents keep the numbers they have; each new sequence continues after the highest
number already given in its series.
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_per_type_tracking_numbers"
down_revision = "0032_user_sb_position"
branch_labels = None
depends_on = None

PREFIXES = ("ORD", "RES", "LTR")


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for prefix in PREFIXES:
        name = f"{prefix.lower()}_tracking_number_seq"
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {name} START WITH 1 INCREMENT BY 1 MINVALUE 1")
        op.execute(sa.text(
            f"SELECT setval('{name}', highest) FROM ("
            "SELECT MAX(CAST(SUBSTR(tracking_number, 5) AS INTEGER)) AS highest FROM documents "
            "WHERE tracking_number ~ :pattern) AS given WHERE highest IS NOT NULL"
        ).bindparams(pattern=f"^{prefix}-[0-9]+$"))
    op.execute("DROP SEQUENCE IF EXISTS document_tracking_number_seq")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE SEQUENCE IF NOT EXISTS document_tracking_number_seq START WITH 1 INCREMENT BY 1 MINVALUE 1")
    for prefix in PREFIXES:
        op.execute(f"DROP SEQUENCE IF EXISTS {prefix.lower()}_tracking_number_seq")
