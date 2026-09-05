"""public identities, catalog lines, and Official sync ledger

Revision ID: 0040_public_identities_official_sync
Revises: 0039_external_catalog_locales
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import text as sql_text

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_foundation.identity import (
    OFFICIAL_DISPLAY_NAME,
    OFFICIAL_HANDLE,
    canonical_slug,
    handle_from_account_id,
    normalize_display_key,
    submitted_display_name,
)

revision: str = "0040_public_identities_official_sync"
down_revision: str | None = "0039_external_catalog_locales"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # This revision id is intentionally descriptive and exceeds Alembic's
    # historical VARCHAR(32) default.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.add_column("account", sa.Column("handle", sa.String(length=32), nullable=True))
    op.add_column("account", sa.Column("handle_normalized", sa.String(length=32), nullable=True))
    op.add_column("account", sa.Column("display_name", sa.String(length=80), nullable=True))
    op.add_column(
        "account", sa.Column("display_name_normalized", sa.String(length=80), nullable=True)
    )
    op.create_table(
        "catalog_identity",
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("owner_account_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=80), nullable=False),
        sa.Column("canonical_name_normalized", sa.String(length=80), nullable=False),
        sa.Column("ownership_revision_id", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("stable_id"),
    )
    op.create_index(
        "ix_catalog_identity_owner_account_id", "catalog_identity", ["owner_account_id"]
    )
    op.create_table(
        "catalog_identity_locale",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("display_name_normalized", sa.String(length=80), nullable=False),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_catalog_identity_locale"),
        sa.ForeignKeyConstraint(["stable_id"], ["catalog_identity.stable_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stable_id", "locale", name="uq_catalog_identity_locale_line"),
    )
    op.create_index(
        "ix_catalog_identity_locale_stable_id", "catalog_identity_locale", ["stable_id"]
    )
    op.add_column(
        "publication_plan",
        sa.Column("expected_ownership_revision_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "report_case",
        sa.Column("locale", sa.String(length=8), server_default="en", nullable=False),
    )
    op.drop_constraint("ck_report_case_topic", "report_case", type_="check")
    op.drop_constraint("ck_report_case_object_kind", "report_case", type_="check")
    op.create_check_constraint(
        "ck_report_case_topic",
        "report_case",
        "topic in ("
        "'object_report', 'service_request', 'country_request', "
        "'component_complaint', 'author_complaint', 'ownership_transfer', "
        "'verification_request', 'other')",
    )
    op.create_check_constraint(
        "ck_report_case_object_kind",
        "report_case",
        "(topic = 'object_report' and object_kind in ('component', 'setup') "
        "and stable_id is not null and version is not null and content_digest is not null) "
        "or (topic in ('component_complaint', 'ownership_transfer') "
        "and stable_id is not null) "
        "or (topic in ("
        "'service_request', 'country_request', 'author_complaint', "
        "'verification_request', 'other'))",
    )
    op.create_check_constraint("ck_report_case_locale", "report_case", "locale in ('ru', 'en')")
    op.add_column(
        "official_upstream_source",
        sa.Column(
            "inventory_state", sa.String(length=16), server_default="enabled", nullable=False
        ),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("update_policy", sa.String(length=16), server_default="daily", nullable=False),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("canonical_name", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("display_name_en", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("display_name_ru", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("manifest_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("ownership_revision_id", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_official_upstream_source_inventory_state",
        "official_upstream_source",
        "inventory_state in ('enabled', 'paused', 'transferred', 'removed')",
    )
    op.create_check_constraint(
        "ck_official_upstream_source_update_policy",
        "official_upstream_source",
        "update_policy in ('daily', 'pinned', 'disabled')",
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("trigger_key", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("state", sa.String(length=32), server_default="desired", nullable=False),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("official_upstream_sync", sa.Column("job_id", sa.Integer(), nullable=True))
    op.add_column(
        "official_upstream_sync",
        sa.Column("outbox_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("expected_owner_account_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("expected_ownership_revision_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("manifest_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("provenance", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("error_class", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "official_upstream_sync",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        "uq_official_upstream_sync_source_day", "official_upstream_sync", type_="unique"
    )
    op.create_unique_constraint(
        "uq_official_upstream_sync_source_trigger",
        "official_upstream_sync",
        ["source_id", "trigger_key"],
    )
    op.create_check_constraint(
        "ck_official_upstream_sync_state",
        "official_upstream_sync",
        "state in ("
        "'desired', 'queued', 'resolving', 'unchanged', 'publishing', 'published', "
        "'retry_wait', 'dead_lettered', 'failed_permanent', 'cancelled_transferred')",
    )
    op.create_table(
        "official_sync_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state in ('pending', 'dispatched', 'cancelled')",
            name="ck_official_sync_outbox_state",
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["official_upstream_sync.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_official_sync_outbox_idempotency"),
    )
    op.create_index("ix_official_sync_outbox_source_id", "official_sync_outbox", ["source_id"])
    op.create_index("ix_official_sync_outbox_attempt_id", "official_sync_outbox", ["attempt_id"])
    op.alter_column(
        "ownership_revision",
        "claim_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.add_column(
        "ownership_revision",
        sa.Column("case_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_ownership_revision_case_id", "ownership_revision", ["case_id"])
    bind = op.get_bind()
    _backfill_accounts(bind)
    _backfill_catalog_identity(bind)
    _backfill_official_sources(bind)
    bind.execute(
        sql_text(
            """
            UPDATE official_upstream_sync
            SET trigger_key = utc_day::text,
                state = CASE result
                    WHEN 'unchanged' THEN 'unchanged'
                    WHEN 'publication_started' THEN 'publishing'
                    ELSE 'retry_wait'
                END
            WHERE trigger_key IS NULL
            """
        )
    )
    conflicts = _collect_conflicts(bind)
    if conflicts:
        detail = "; ".join(f"{item['kind']}:{item['key']}:{item['ids']}" for item in conflicts[:20])
        raise RuntimeError(f"AI_STP_MIGRATION_CONFLICT: {detail}")
    op.create_index(
        "uq_account_handle_normalized",
        "account",
        ["handle_normalized"],
        unique=True,
        postgresql_where=sa.text("handle_normalized IS NOT NULL"),
    )
    op.create_index(
        "uq_account_display_name_normalized",
        "account",
        ["display_name_normalized"],
        unique=True,
        postgresql_where=sa.text("display_name_normalized IS NOT NULL"),
    )
    op.create_unique_constraint(
        "uq_catalog_identity_canonical",
        "catalog_identity",
        ["canonical_name_normalized"],
    )
    op.create_unique_constraint(
        "uq_catalog_identity_locale_name",
        "catalog_identity_locale",
        ["locale", "display_name_normalized"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_catalog_identity_locale_name", "catalog_identity_locale", type_="unique")
    op.drop_constraint("uq_catalog_identity_canonical", "catalog_identity", type_="unique")
    op.drop_index("uq_account_display_name_normalized", table_name="account")
    op.drop_index("uq_account_handle_normalized", table_name="account")
    op.drop_index("ix_ownership_revision_case_id", table_name="ownership_revision")
    op.drop_column("ownership_revision", "case_id")
    op.alter_column(
        "ownership_revision",
        "claim_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.drop_index("ix_official_sync_outbox_attempt_id", table_name="official_sync_outbox")
    op.drop_index("ix_official_sync_outbox_source_id", table_name="official_sync_outbox")
    op.drop_table("official_sync_outbox")
    op.drop_constraint("ck_official_upstream_sync_state", "official_upstream_sync", type_="check")
    op.drop_constraint(
        "uq_official_upstream_sync_source_trigger", "official_upstream_sync", type_="unique"
    )
    op.create_unique_constraint(
        "uq_official_upstream_sync_source_day",
        "official_upstream_sync",
        ["source_id", "utc_day"],
    )
    for column in (
        "cancelled_at",
        "completed_at",
        "started_at",
        "error_class",
        "provenance",
        "manifest_digest",
        "expected_ownership_revision_id",
        "expected_owner_account_id",
        "outbox_id",
        "job_id",
        "retry_at",
        "attempt_count",
        "state",
        "trigger_key",
    ):
        op.drop_column("official_upstream_sync", column)
    op.drop_constraint(
        "ck_official_upstream_source_update_policy",
        "official_upstream_source",
        type_="check",
    )
    op.drop_constraint(
        "ck_official_upstream_source_inventory_state",
        "official_upstream_source",
        type_="check",
    )
    for column in (
        "ownership_revision_id",
        "manifest_digest",
        "display_name_ru",
        "display_name_en",
        "canonical_name",
        "update_policy",
        "inventory_state",
    ):
        op.drop_column("official_upstream_source", column)
    op.drop_constraint("ck_report_case_locale", "report_case", type_="check")
    op.drop_constraint("ck_report_case_object_kind", "report_case", type_="check")
    op.drop_constraint("ck_report_case_topic", "report_case", type_="check")
    op.create_check_constraint(
        "ck_report_case_topic",
        "report_case",
        "topic in ('object_report', 'service_request', 'country_request')",
    )
    op.create_check_constraint(
        "ck_report_case_object_kind",
        "report_case",
        "(topic = 'object_report' and object_kind in ('component', 'setup') "
        "and stable_id is not null and version is not null and content_digest is not null) "
        "or (topic <> 'object_report' and object_kind is null and stable_id is null "
        "and version is null and content_digest is null)",
    )
    op.drop_column("report_case", "locale")
    op.drop_column("publication_plan", "expected_ownership_revision_id")
    op.drop_index("ix_catalog_identity_locale_stable_id", table_name="catalog_identity_locale")
    op.drop_table("catalog_identity_locale")
    op.drop_index("ix_catalog_identity_owner_account_id", table_name="catalog_identity")
    op.drop_table("catalog_identity")
    op.drop_column("account", "display_name_normalized")
    op.drop_column("account", "display_name")
    op.drop_column("account", "handle_normalized")
    op.drop_column("account", "handle")


def _backfill_accounts(bind: sa.Connection) -> None:
    rows = bind.execute(sql_text("SELECT id FROM account")).fetchall()
    used_handles: set[str] = set()
    used_displays: set[str] = set()
    for (account_id,) in rows:
        if account_id == OFFICIAL_ACCOUNT_ID:
            handle = OFFICIAL_HANDLE
            display = OFFICIAL_DISPLAY_NAME
        else:
            handle = handle_from_account_id(str(account_id))
            display = f"User {handle.removeprefix('user-')}"
        handle_key = handle
        display_key = normalize_display_key(display)
        if handle_key in used_handles or display_key in used_displays:
            raise RuntimeError(
                "AI_STP_MIGRATION_CONFLICT: generated account identity collision: "
                f"{account_id}:{handle_key}:{display_key}"
            )
        used_handles.add(handle_key)
        used_displays.add(display_key)
        bind.execute(
            sql_text(
                """
                UPDATE account
                SET handle = :handle,
                    handle_normalized = :handle_key,
                    display_name = :display,
                    display_name_normalized = :display_key
                WHERE id = :account_id AND handle IS NULL
                """
            ),
            {
                "handle": handle,
                "handle_key": handle_key,
                "display": submitted_display_name(display),
                "display_key": display_key,
                "account_id": account_id,
            },
        )


def _backfill_catalog_identity(bind: sa.Connection) -> None:
    rows = bind.execute(
        sql_text(
            """
            SELECT DISTINCT ON (stable_id)
                stable_id, owner_account_id, name
            FROM catalog_metadata
            WHERE object_kind = 'component'
            ORDER BY stable_id, published_at DESC NULLS LAST, id DESC
            """
        )
    ).fetchall()
    for stable_id, owner_account_id, name in rows:
        raw = str(name or "").strip()
        if not raw:
            raise RuntimeError(f"AI_STP_MIGRATION_CONFLICT: component_name_missing:{stable_id}")
        try:
            slug = canonical_slug(raw)
        except ValueError:
            raise RuntimeError(
                f"AI_STP_MIGRATION_CONFLICT: component_name_invalid:{stable_id}"
            ) from None
        spelling = submitted_display_name(raw)
        bind.execute(
            sql_text(
                """
                INSERT INTO catalog_identity (
                    stable_id, owner_account_id, canonical_name,
                    canonical_name_normalized, ownership_revision_id
                )
                VALUES (:stable_id, :owner_id, :canonical, :canonical_key, '')
                ON CONFLICT (stable_id) DO NOTHING
                """
            ),
            {
                "stable_id": stable_id,
                "owner_id": owner_account_id,
                "canonical": slug,
                "canonical_key": slug,
            },
        )
        for locale in ("en", "ru"):
            key = normalize_display_key(spelling)
            bind.execute(
                sql_text(
                    """
                    INSERT INTO catalog_identity_locale (
                        stable_id, locale, display_name, display_name_normalized
                    )
                    VALUES (:stable_id, :locale, :display, :display_key)
                    ON CONFLICT (stable_id, locale) DO NOTHING
                    """
                ),
                {
                    "stable_id": stable_id,
                    "locale": locale,
                    "display": spelling,
                    "display_key": key,
                },
            )


def _backfill_official_sources(bind: sa.Connection) -> None:
    bind.execute(
        sql_text(
            """
            UPDATE official_upstream_source
            SET inventory_state = CASE WHEN enabled THEN 'enabled' ELSE 'paused' END,
                canonical_name = COALESCE(canonical_name, lower(replace(name, ' ', '-'))),
                display_name_en = COALESCE(display_name_en, name),
                display_name_ru = COALESCE(display_name_ru, name)
            """
        )
    )


def _collect_conflicts(bind: sa.Connection) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    mixed = bind.execute(
        sql_text(
            """
            SELECT stable_id,
                   string_agg(DISTINCT owner_account_id, ',' ORDER BY owner_account_id)
            FROM catalog_metadata
            WHERE object_kind = 'component'
            GROUP BY stable_id
            HAVING COUNT(DISTINCT owner_account_id) > 1
            """
        )
    ).fetchall()
    for stable_id, owners in mixed:
        conflicts.append({"kind": "mixed_owner", "key": str(stable_id), "ids": str(owners)})
    handles = bind.execute(
        sql_text(
            """
            SELECT handle_normalized, string_agg(id, ',' ORDER BY id)
            FROM account
            WHERE handle_normalized IS NOT NULL
            GROUP BY handle_normalized
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    for key, ids in handles:
        conflicts.append({"kind": "handle", "key": str(key), "ids": str(ids)})
    displays = bind.execute(
        sql_text(
            """
            SELECT display_name_normalized, string_agg(id, ',' ORDER BY id)
            FROM account
            WHERE display_name_normalized IS NOT NULL
            GROUP BY display_name_normalized
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    for key, ids in displays:
        conflicts.append({"kind": "account_display", "key": str(key), "ids": str(ids)})
    canonicals = bind.execute(
        sql_text(
            """
            SELECT canonical_name_normalized, string_agg(stable_id, ',' ORDER BY stable_id)
            FROM catalog_identity
            GROUP BY canonical_name_normalized
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    for key, ids in canonicals:
        conflicts.append({"kind": "canonical", "key": str(key), "ids": str(ids)})
    locales = bind.execute(
        sql_text(
            """
            SELECT locale, display_name_normalized,
                   string_agg(stable_id, ',' ORDER BY stable_id)
            FROM catalog_identity_locale
            GROUP BY locale, display_name_normalized
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    for locale, key, ids in locales:
        conflicts.append({"kind": f"locale_{locale}", "key": str(key), "ids": str(ids)})
    return conflicts
