"""Join grant receipts and scan journal deletion without rewriting either history."""

revision = "0125_merge_grants_scan"
down_revision = ("0124_grant_operation_receipts", "0124_scan_journal_deletion")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
