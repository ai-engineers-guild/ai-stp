"""Replay the revisions a reordered history let applied databases skip.

The reports/heartbeat merge (`2b2ea703`, 2026-09-27) re-chained
`0096_device_session_semantics` — already applied in production — after the
feature's `0096_heartbeat_reports` … `0106_technology_review_queue`. Alembic
counts every ancestor of the stamped revision as applied, so a database that
had passed `0096_device_session_semantics` before the merge reached `0111`
without those eleven revisions: production had no heartbeat, inventory or
operation-fact tables, missed four `telemetry_policy` and two
`runtime_usage_event` columns, and its telemetry retention job dead-lettered
daily on `installation_operation_fact` from 2026-09-30.

Each skipped revision runs here through its own `upgrade()` when the object it
creates first is absent, in chain order. A database that ran the chain in
order has every sentinel, and this revision changes nothing on it. The
permission grants of `0104` carry no sentinel of their own; they are replayed
only when the chain was skipped, so a complete database does not grant them to
roles created after `0104` ran.
"""

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import context, op
from alembic.script import ScriptDirectory

revision: str = "0112_replay_skipped_feature_chain"
down_revision: str | Sequence[str] | None = "0111_corporate_access_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

type Present = Callable[[sa.Inspector], bool]


def _table(name: str) -> Present:
    return lambda inspector: inspector.has_table(name)


def _column(table: str, name: str) -> Present:
    def present(inspector: sa.Inspector) -> bool:
        if not inspector.has_table(table):
            return False
        return name in {column["name"] for column in inspector.get_columns(table)}

    return present


def _check(table: str, name: str) -> Present:
    return lambda inspector: (
        name in {constraint["name"] for constraint in inspector.get_check_constraints(table)}
    )


#: The skipped chain in order, each with the object its upgrade creates first.
SKIPPED: tuple[tuple[str, Present | None], ...] = (
    ("0096_heartbeat_reports", _table("installation_heartbeat_event")),
    ("0097_installation_operation_facts", _table("installation_operation_fact")),
    ("0098_inventory_scan_policy", _column("telemetry_policy", "inventory_scan_enabled")),
    ("0099_installation_inventory", _table("installation_inventory_snapshot")),
    ("0100_usage_evidence_source", _column("runtime_usage_event", "source")),
    (
        "0101_direct_component_usage",
        _check("runtime_usage_event", "ck_runtime_usage_setup_coordinate"),
    ),
    ("0102_usage_collection_policy", _column("telemetry_policy", "usage_collection_enabled")),
    ("0103_report_timezone", _column("telemetry_policy", "report_timezone")),
    ("0104_project_link_permissions", None),
    ("0105_technology_unmapped_coordinates", _table("technology_unmapped_coordinate")),
    (
        "0106_technology_review_queue",
        _column("technology_unmapped_coordinate", "candidate_technology_id"),
    ),
)


def upgrade() -> None:
    scripts = ScriptDirectory.from_config(context.config)
    chain_skipped = not sa.inspect(op.get_bind()).has_table("installation_heartbeat_event")
    for skipped_revision, present in SKIPPED:
        # A fresh inspector per step: each replay changes what the next sees.
        inspector = sa.inspect(op.get_bind())
        replay = chain_skipped if present is None else not present(inspector)
        if not replay:
            continue
        script = scripts.get_revision(skipped_revision)
        if script is None:
            raise RuntimeError(f"skipped revision {skipped_revision} is not in the history")
        script.module.upgrade()


def downgrade() -> None:
    # Whatever this revision created belongs to the replayed revisions, whose
    # own downgrades remove it when the history is walked below `0096`.
    pass
