"""Global uniqueness for device.public_key.

A device key identifies one device globally: the same Ed25519 key must never
appear under two accounts. The old (account_id, public_key) composite let two
accounts race the same key past both application checks; this constraint is
the arbiter the checks could not be. Existing duplicates fail the upgrade
loudly — silently merging a credential-bearing row is not a decision a
migration may take.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0107_device_public_key_global"
down_revision: str | None = "0097_profile_publish_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "device"


def upgrade() -> None:
    op.drop_constraint("uq_device_account_public_key", TABLE, type_="unique")
    op.create_unique_constraint("uq_device_public_key", TABLE, ["public_key"])


def downgrade() -> None:
    op.drop_constraint("uq_device_public_key", TABLE, type_="unique")
    op.create_unique_constraint("uq_device_account_public_key", TABLE, ["account_id", "public_key"])
