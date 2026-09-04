"""Aggregate invariants for the recoverable multi-root coordinator."""

from __future__ import annotations

import sqlite3

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal, multi_root


class Coordinator:
    """Keep aggregate claims no stronger than the durable child journals."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def plan(
        self,
        *,
        setup_stable_id: str,
        setup_version: str,
        harness_id: str,
        children: tuple[multi_root.Child, ...],
        idempotency_key: str,
        at: str,
    ) -> multi_root.MultiRootTransaction:
        return multi_root.propose(
            self.connection,
            setup_stable_id=setup_stable_id,
            setup_version=setup_version,
            harness_id=harness_id,
            children=children,
            idempotency_key=idempotency_key,
            at=at,
        )

    def approve(
        self, transaction_id: str, *, expected_digest: str, at: str
    ) -> multi_root.MultiRootTransaction:
        return multi_root.approve(
            self.connection,
            transaction_id,
            expected_digest=expected_digest,
            at=at,
        )

    def begin(self, transaction_id: str, *, at: str) -> multi_root.MultiRootTransaction:
        held = multi_root.get(self.connection, transaction_id)
        if held.approved_digest != held.digest:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the exact multi-root transaction has not been approved",
            )
        return multi_root.move(
            self.connection,
            transaction_id,
            expected=frozenset({"planned"}),
            state="applying",
            result="all child plans were approved",
            at=at,
        )

    def observe_child(
        self, transaction_id: str, operation_id: str, *, at: str
    ) -> multi_root.MultiRootTransaction:
        current = journal.get(self.connection, operation_id)
        if current is None:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "a multi-root child operation disappeared from the journal",
            )
        return multi_root.record_child(
            self.connection,
            transaction_id,
            operation_id,
            state=current.state,
            backup_ref=installation.backup_reference(self.connection, operation_id),
            at=at,
        )

    def record_compensated(
        self, transaction_id: str, operation_id: str, *, backup_ref: str, at: str
    ) -> multi_root.MultiRootTransaction:
        """Record exact restoration of one original child after its rollback verified."""
        return multi_root.record_child(
            self.connection,
            transaction_id,
            operation_id,
            state=installation.STATE_ROLLED_BACK,
            backup_ref=backup_ref,
            at=at,
        )

    def begin_compensation(
        self, transaction_id: str, *, at: str
    ) -> multi_root.MultiRootTransaction:
        return multi_root.move(
            self.connection,
            transaction_id,
            expected=frozenset({"applying", "recovery_required"}),
            state="compensating",
            result="a child did not reach its verified postcondition",
            at=at,
        )

    def finish_verified(self, transaction_id: str, *, at: str) -> multi_root.MultiRootTransaction:
        held = multi_root.get(self.connection, transaction_id)
        if not held.children or any(
            child.state != installation.STATE_VERIFIED for child in held.children
        ):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "multi-root success requires every child postcondition",
            )
        return multi_root.move(
            self.connection,
            transaction_id,
            expected=frozenset({"applying"}),
            state="verified",
            result="every child postcondition is verified",
            at=at,
        )

    def finish_rolled_back(
        self, transaction_id: str, *, at: str
    ) -> multi_root.MultiRootTransaction:
        held = multi_root.get(self.connection, transaction_id)
        unsettled = {
            installation.STATE_APPLYING,
            installation.STATE_APPLIED_UNVERIFIED,
            installation.STATE_PARTIAL,
            installation.STATE_VERIFIED,
        }
        if any(child.state in unsettled for child in held.children):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "multi-root rollback requires every possible effect to be settled",
            )
        return multi_root.move(
            self.connection,
            transaction_id,
            expected=frozenset({"compensating"}),
            state="rolled_back",
            result="every possible child effect was restored or proved absent",
            at=at,
        )

    def require_recovery(
        self, transaction_id: str, *, at: str, reason: str
    ) -> multi_root.MultiRootTransaction:
        return multi_root.move(
            self.connection,
            transaction_id,
            expected=frozenset({"applying", "compensating", "recovery_required"}),
            state="recovery_required",
            result=reason,
            at=at,
        )

    def owns(self, operation_id: str) -> bool:
        return multi_root.child_is_owned(self.connection, operation_id)
