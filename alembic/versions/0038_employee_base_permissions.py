"""Every employee except an office user gets the basic document permissions.

View, search, filter, view details, download and print documents. An office user (an Employee
with an office and only office workflow permissions) keeps only its office permissions.
"""

import ast
import json

from alembic import op
import sqlalchemy as sa


revision = "0038_employee_base_permissions"
down_revision = "0037_user_delete_keeps_handoffs"
branch_labels = None
depends_on = None

BASE = ["view_documents", "search_documents", "filter_documents", "view_document_details", "download_documents", "print_documents"]
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
    rows = bind.execute(sa.text("SELECT id, role, office_id, permissions FROM users")).fetchall()
    for user_id, role, office_id, value in rows:
        permissions = _parse_permissions(value)
        if permissions is None or str(role or "").strip().lower() not in EMPLOYEE_ROLES or "*" in permissions:
            continue
        if office_id is not None and set(permissions) <= OFFICE:
            continue  # an office user
        missing = [permission for permission in BASE if permission not in permissions]
        if missing:
            bind.execute(sa.text("UPDATE users SET permissions = :permissions WHERE id = :id"),
                         {"permissions": str(sorted(permissions + missing)), "id": user_id})


def downgrade():
    pass  # the added permissions can't be told apart from ones given by hand
