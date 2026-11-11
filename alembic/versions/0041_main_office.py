"""Mark the main office; employees in any other office keep only office permissions.

The main office is the one whose employees already hold more than office permissions (the most
such employees wins). With no such office, none is marked and no account is changed.
"""

import ast
import json
from collections import Counter

from alembic import op
import sqlalchemy as sa


revision = "0041_main_office"
down_revision = "0040_documents_foreign_keys"
branch_labels = None
depends_on = None

OFFICE = {
    "view_office_documents", "search_office_documents", "view_office_document_details", "scan_qr",
    "pass_office_documents", "confirm_document_receipt", "view_office_history",
}
EMPLOYEE_ROLES = {"employee", "staff", "secretary / vice mayor", "secretary"}


def _parse_permissions(value):
    text = (value or "").strip()
    if not text:
        return []
    for parse in (json.loads, ast.literal_eval):
        try:
            parsed = parse(text)
        except Exception:
            continue
        if isinstance(parsed, (list, tuple, set)):
            return [str(item) for item in parsed]
    return None


def upgrade():
    bind = op.get_bind()
    if "is_main" not in {column["name"] for column in sa.inspect(bind).get_columns("offices")}:
        op.add_column("offices", sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.false()))
    if bind.execute(sa.text("SELECT 1 FROM offices WHERE is_main = :yes"), {"yes": True}).first():
        return  # a main office was already chosen

    employees = [
        (user_id, office_id, _parse_permissions(value))
        for user_id, role, office_id, value in bind.execute(
            sa.text("SELECT id, role, office_id, permissions FROM users WHERE office_id IS NOT NULL")
        ).fetchall()
        if str(role or "").strip().lower() in EMPLOYEE_ROLES
    ]
    staff_offices = Counter(office_id for _, office_id, permissions in employees
                            if permissions is not None and not set(permissions) <= OFFICE)
    if not staff_offices:
        return
    main_office_id = staff_offices.most_common(1)[0][0]
    bind.execute(sa.text("UPDATE offices SET is_main = :yes WHERE id = :id"), {"yes": True, "id": main_office_id})
    for user_id, office_id, permissions in employees:
        if office_id == main_office_id or permissions is None or set(permissions) <= OFFICE:
            continue
        kept = sorted(set(permissions) & OFFICE) or sorted(OFFICE)
        bind.execute(sa.text("UPDATE users SET permissions = :permissions WHERE id = :id"),
                     {"permissions": str(kept), "id": user_id})


def downgrade():
    # Stripped permissions aren't restored: they were the loophole.
    op.drop_column("offices", "is_main")
