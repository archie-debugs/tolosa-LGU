"""Record the public portal migration point without changing the legacy schema."""

from alembic import op


revision = "0004_add_public_document_visibility"
down_revision = "0003_add_last_login"
branch_labels = None
depends_on = None


def upgrade():
	pass


def downgrade():
	pass
