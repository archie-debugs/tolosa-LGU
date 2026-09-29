"""add legislative document number and series year"""
import re

from alembic import op
import sqlalchemy as sa


revision = "0010_doc_legislative_meta"
down_revision = "0009_user_sessions_cascade"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("document_number", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("series_year", sa.Integer(), nullable=True))

    documents = sa.table(
        "documents",
        sa.column("id", sa.Integer()),
        sa.column("title", sa.String()),
        sa.column("document_number", sa.String()),
        sa.column("series_year", sa.Integer()),
    )
    number_pattern = re.compile(r"(?i)\b(?:ordinance|resolution)\s+(?:no\.?|number)\s*[:#]?\s*([0-9]+)\b")
    year_pattern = re.compile(r"(?i)\bseries\s*:?\s*((?:19|20)[0-9]{2})\b")
    connection = op.get_bind()
    for row in connection.execute(sa.select(documents.c.id, documents.c.title)):
        title = row.title or ""
        number_match = number_pattern.search(title)
        year_match = year_pattern.search(title)
        if number_match or year_match:
            values = {}
            if number_match:
                values["document_number"] = number_match.group(1)
            if year_match:
                values["series_year"] = int(year_match.group(1))
            connection.execute(
                documents.update().where(documents.c.id == row.id).values(**values)
            )


def downgrade():
    op.drop_column("documents", "series_year")
    op.drop_column("documents", "document_number")