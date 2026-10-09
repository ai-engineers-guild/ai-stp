-- Current schema 53; one clean bootstrap, without historical migrations.

CREATE TABLE acquired_trust (
    stable_id          TEXT NOT NULL REFERENCES entity(stable_id),
    version            TEXT NOT NULL,
    passport_digest    TEXT NOT NULL,
    trust_lane         TEXT NOT NULL,
    author_verified    INTEGER NOT NULL,
    component_verified INTEGER NOT NULL,
    acquired_at        TEXT NOT NULL,
    PRIMARY KEY (stable_id, version)
) STRICT;

CREATE TABLE agent_task (
    task_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    intent TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'planned', 'blocked', 'running',
            'completed', 'failed', 'cancelled'
        )
    ),
    goal_satisfied INTEGER NOT NULL CHECK (goal_satisfied IN (0, 1)),
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    outcome_json TEXT,
    questions_json TEXT NOT NULL,
    child_operation_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
, harness_id TEXT NOT NULL DEFAULT '', project_root TEXT NOT NULL DEFAULT '', scope TEXT NOT NULL DEFAULT '', account_id TEXT NOT NULL DEFAULT '', precondition_digest TEXT NOT NULL DEFAULT '', original_request_json TEXT NOT NULL DEFAULT '', cancel_requested_at TEXT NOT NULL DEFAULT '') STRICT;

CREATE TABLE backup_ref (
    backup_id    TEXT PRIMARY KEY,
    harness_id   TEXT NOT NULL,
    target_id    TEXT NOT NULL,
    provider_ref TEXT NOT NULL,
    created_at   TEXT NOT NULL
) STRICT;

CREATE TABLE component_source_binding (
    source_key     TEXT PRIMARY KEY,
    stable_id      TEXT NOT NULL UNIQUE
        REFERENCES entity(stable_id),
    harness_id     TEXT NOT NULL,
    component_type TEXT NOT NULL,
    absolute_path  TEXT NOT NULL,
    created_at     TEXT NOT NULL
) STRICT;

CREATE TABLE "consent" (
    consent_id  TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    scope       TEXT NOT NULL,
    target      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    observed    TEXT NOT NULL DEFAULT '[]',
    decided_by  TEXT NOT NULL,
    origin      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    revoked_at  TEXT,
    PRIMARY KEY (account_id, consent_id),
    UNIQUE (account_id, scope, target)
) STRICT;

CREATE TABLE content (
    digest      TEXT PRIMARY KEY,
    bytes       BLOB NOT NULL,
    byte_length INTEGER NOT NULL,
    stored_at   TEXT NOT NULL
) STRICT;

CREATE TABLE corporate_inventory_outbox (
    scan_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE entity (
    stable_id  TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE eval_plan (
    plan_id       TEXT PRIMARY KEY,
    plan_digest   TEXT NOT NULL UNIQUE,
    document_json TEXT NOT NULL,
    created_at    TEXT NOT NULL
) STRICT;

CREATE TABLE eval_result (
    run_id         TEXT PRIMARY KEY,
    plan_id        TEXT NOT NULL UNIQUE REFERENCES eval_plan(plan_id),
    result_digest  TEXT NOT NULL UNIQUE,
    document_json  TEXT NOT NULL,
    executed_at    TEXT NOT NULL
) STRICT;

CREATE TABLE fork_origin (
    stable_id        TEXT PRIMARY KEY REFERENCES entity(stable_id),
    source_stable_id TEXT NOT NULL,
    source_version   TEXT NOT NULL,
    source_digest    TEXT NOT NULL,
    created_at       TEXT NOT NULL
) STRICT;

CREATE TABLE github_repository_observation (
    observation_id      INTEGER PRIMARY KEY,
    stable_id           TEXT NOT NULL REFERENCES entity(stable_id),
    version             TEXT NOT NULL,
    passport_digest     TEXT NOT NULL,
    source_repository   TEXT NOT NULL,
    repository_id       INTEGER NOT NULL,
    repository_full_name TEXT NOT NULL,
    archived            INTEGER NOT NULL CHECK (archived IN (0, 1)),
    etag                TEXT,
    fetched_at          TEXT NOT NULL,
    expires_at          TEXT NOT NULL,
    response_kind       TEXT NOT NULL
        CHECK (response_kind IN ('modified', 'not_modified'))
) STRICT;

CREATE TABLE head (
    stable_id   TEXT NOT NULL REFERENCES entity(stable_id),
    revision_id TEXT NOT NULL REFERENCES revision(revision_id),
    PRIMARY KEY (stable_id, revision_id)
) STRICT;

CREATE TABLE heartbeat_subscription (
    organization_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    next_attempt_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_attempt_at TEXT,
    last_success_at TEXT,
    attempt_token TEXT
, scheduler_interval_seconds INTEGER) STRICT;

CREATE TABLE "installation_transaction" (
    transaction_id      TEXT PRIMARY KEY,
    idempotency_key     TEXT NOT NULL UNIQUE,
    transaction_digest TEXT NOT NULL UNIQUE,
    setup_stable_id     TEXT NOT NULL,
    setup_version       TEXT NOT NULL,
    harness_id          TEXT NOT NULL,
    state               TEXT NOT NULL CHECK (
        state IN (
            'planned', 'applying', 'compensating',
            'recovery_required', 'verified', 'rolled_back',
            'cancelled'
        )
    ),
    approved_digest     TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
, transaction_kind TEXT NOT NULL DEFAULT 'single_setup' CHECK (transaction_kind IN ('single_setup', 'environment'))) STRICT;

CREATE TABLE "installation_transaction_child" (
    transaction_id TEXT NOT NULL REFERENCES installation_transaction(transaction_id),
    position INTEGER NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'user_root', 'project')),
    operation_id TEXT NOT NULL UNIQUE REFERENCES operation_plan(operation_id),
    target_id TEXT NOT NULL,
    plan_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    backup_ref TEXT,
    undo_operation_id TEXT,
    PRIMARY KEY (transaction_id, position),
    UNIQUE (transaction_id, target_id)
) STRICT;

CREATE TABLE installation_transaction_event (
    transaction_id TEXT NOT NULL
        REFERENCES installation_transaction(transaction_id),
    sequence       INTEGER NOT NULL,
    at             TEXT NOT NULL,
    state_before   TEXT NOT NULL,
    state_after    TEXT NOT NULL,
    result         TEXT NOT NULL,
    PRIMARY KEY (transaction_id, sequence)
) STRICT;

CREATE TABLE installation_transaction_resource (
    resource_digest TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    transaction_id  TEXT NOT NULL
        REFERENCES installation_transaction(transaction_id),
    is_exact        INTEGER NOT NULL CHECK (is_exact IN (0, 1)),
    PRIMARY KEY (resource_digest, target_id)
) STRICT;

CREATE TABLE installation_transaction_target (
    target_id      TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL
        REFERENCES installation_transaction(transaction_id)
) STRICT;

CREATE TABLE object_version (
    stable_id       TEXT NOT NULL REFERENCES entity(stable_id),
    version         TEXT NOT NULL,
    major           INTEGER NOT NULL,
    minor           INTEGER NOT NULL,
    passport_digest TEXT NOT NULL,
    revision_id     TEXT NOT NULL REFERENCES revision(revision_id),
    created_at      TEXT NOT NULL,
    PRIMARY KEY (stable_id, version)
) STRICT;

CREATE TABLE operation (
    operation_id TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    state        TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    detail       TEXT
) STRICT;

CREATE TABLE operation_corporate_binding (
    operation_id TEXT PRIMARY KEY REFERENCES operation(operation_id),
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('global','project','unknown')),
    created_at TEXT NOT NULL,
    delivered_at TEXT
) STRICT;

CREATE TABLE operation_event (
    operation_id TEXT NOT NULL REFERENCES operation(operation_id),
    sequence     INTEGER NOT NULL,
    at           TEXT NOT NULL,
    state_before TEXT NOT NULL,
    state_after  TEXT NOT NULL,
    result       TEXT NOT NULL,
    evidence     TEXT, global_sequence INTEGER,
    PRIMARY KEY (operation_id, sequence)
) STRICT;

CREATE TABLE operation_plan (
    operation_id           TEXT PRIMARY KEY REFERENCES operation(operation_id),
    idempotency_key        TEXT NOT NULL UNIQUE,
    action                 TEXT NOT NULL,
    author                 TEXT NOT NULL,
    target_id              TEXT NOT NULL,
    expected_target_digest TEXT NOT NULL,
    provider_version       TEXT NOT NULL,
    effects                TEXT NOT NULL,
    confirmation           TEXT NOT NULL,
    recovery_action        TEXT NOT NULL,
    plan_digest            TEXT NOT NULL,
    expires_at             TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    approved_digest        TEXT,
    backup_ref             TEXT
, setup_stable_id TEXT, setup_version TEXT, verified_target_digest TEXT, provider_protocol_version INTEGER, provider_target TEXT, plan_schema_version INTEGER, provider_release_manifest TEXT, provider_release_recovery INTEGER NOT NULL DEFAULT 0, bundle_format TEXT, bundle_digest TEXT, bundle_artifact_digest TEXT, bundle_size INTEGER, provider_plan_digest TEXT, provider_release_trust TEXT, provider_release_evidence TEXT, program_version TEXT, program_entry_point TEXT, program_harness_id TEXT, program_entry_point_planned TEXT, program_prefix_state TEXT, provider_artifact_digest TEXT, target_scope TEXT) STRICT;

CREATE TABLE overlay_origin (
    revision_id TEXT PRIMARY KEY REFERENCES revision(revision_id),
    source_kind TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    base_digest TEXT NOT NULL,
    applied_at  TEXT NOT NULL
) STRICT;

CREATE TABLE preserved_setup (
    stable_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE REFERENCES operation_plan(operation_id),
    target_id TEXT NOT NULL,
    provider_target TEXT NOT NULL,
    target_scope TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    backup_ref TEXT NOT NULL,
    snapshot_digest TEXT NOT NULL,
    roots TEXT NOT NULL,
    excluded TEXT NOT NULL,
    created_at TEXT NOT NULL
, base_root TEXT NOT NULL DEFAULT 'target' CHECK (base_root IN ('target', 'parent'))) STRICT;

CREATE TABLE project_ledger_push (
    local_project_id TEXT NOT NULL,
    link_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'pending', 'accepted', 'conflict', 'rejected',
            'superseded', 'failed', 'unknown'
        )
    ),
    receipt_json TEXT,
    PRIMARY KEY (local_project_id, idempotency_key)
) STRICT;

CREATE TABLE project_ledger_revision (
    revision_id TEXT NOT NULL,
    local_project_id TEXT NOT NULL,
    link_id TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('pushed', 'pulled')),
    view_json TEXT NOT NULL,
    PRIMARY KEY (local_project_id, revision_id)
) STRICT;

CREATE TABLE project_link (
    local_project_id TEXT PRIMARY KEY REFERENCES entity(stable_id),
    organization_id TEXT NOT NULL,
    remote_project_id TEXT NOT NULL,
    provider_project_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('linked', 'unlinked', 'conflict')),
    local_revision TEXT NOT NULL,
    remote_revision TEXT NOT NULL,
    provider_revision TEXT,
    link_revision INTEGER NOT NULL CHECK (link_revision >= 1),
    updated_at TEXT NOT NULL
, plan_id TEXT NOT NULL DEFAULT '', plan_digest TEXT NOT NULL DEFAULT '', link_id TEXT NOT NULL DEFAULT '') STRICT;

CREATE TABLE project_root (
    root      TEXT PRIMARY KEY,
    stable_id TEXT NOT NULL UNIQUE REFERENCES entity(stable_id)
) STRICT;

CREATE TABLE project_sync_plan (
    plan_id TEXT PRIMARY KEY,
    local_project_id TEXT NOT NULL REFERENCES project_link(local_project_id),
    state TEXT NOT NULL CHECK (
        state IN ('ready', 'conflict', 'applied', 'failed', 'unknown')
    ),
    action TEXT NOT NULL CHECK (
        action IN ('noop', 'local_to_remote', 'remote_to_local', 'merge_required')
    ),
    expected_link_revision INTEGER NOT NULL CHECK (expected_link_revision >= 1),
    local_revision TEXT NOT NULL,
    remote_revision TEXT NOT NULL,
    provider_revision TEXT,
    conflict_code TEXT,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL, common_ancestor_revision TEXT, plan_digest TEXT NOT NULL DEFAULT '', expires_at TEXT NOT NULL DEFAULT '', apply_idempotency_key TEXT, apply_state TEXT, apply_receipt_json TEXT, link_id TEXT NOT NULL DEFAULT '',
    UNIQUE (local_project_id, idempotency_key)
) STRICT;

CREATE TABLE proposal (
    proposal_id         TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES entity(stable_id),
    harness_id          TEXT NOT NULL,
    snapshot            TEXT NOT NULL,
    graph               TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    expires_at          TEXT NOT NULL,
    cancelled_at        TEXT,
    confirmed_stable_id TEXT,
    confirmed_version   TEXT
) STRICT;

CREATE TABLE provider_installation (
    harness_id        TEXT PRIMARY KEY,
    path              TEXT NOT NULL,
    source            TEXT NOT NULL,
    state             TEXT NOT NULL,
    provider_id       TEXT NOT NULL,
    provider_version  TEXT NOT NULL,
    tag               TEXT NOT NULL,
    commit_sha        TEXT NOT NULL,
    artifact_digest   TEXT NOT NULL,
    checked_at        TEXT NOT NULL,
    source_checked_at TEXT NOT NULL
) STRICT;

CREATE TABLE provider_release_floor (
    provider_id      TEXT PRIMARY KEY,
    minimum_sequence INTEGER NOT NULL,
    artifact_digest  TEXT NOT NULL,
    advanced_at      TEXT NOT NULL
) STRICT;

CREATE TABLE recommendation_trace (
    stable_id   TEXT NOT NULL REFERENCES entity(stable_id),
    version     TEXT NOT NULL,
    proposal_id TEXT NOT NULL REFERENCES proposal(proposal_id),
    snapshot    TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (stable_id, version)
) STRICT;

CREATE TABLE report_plan (
    plan_id          TEXT PRIMARY KEY,
    plan_digest      TEXT NOT NULL UNIQUE,
    request_json     TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    submitted_case   TEXT
) STRICT;

CREATE TABLE revision (
    revision_id  TEXT PRIMARY KEY,
    stable_id    TEXT NOT NULL REFERENCES entity(stable_id),
    content      TEXT NOT NULL,
    device_id    TEXT NOT NULL,
    operation_id TEXT,
    created_at   TEXT NOT NULL
) STRICT;

CREATE TABLE revision_parent (
    revision_id        TEXT NOT NULL REFERENCES revision(revision_id),
    parent_revision_id TEXT NOT NULL REFERENCES revision(revision_id),
    PRIMARY KEY (revision_id, parent_revision_id)
) STRICT;

CREATE TABLE selected_version (
    project_id  TEXT NOT NULL REFERENCES entity(stable_id),
    harness_id  TEXT NOT NULL,
    stable_id   TEXT NOT NULL REFERENCES entity(stable_id),
    version     TEXT NOT NULL,
    state       TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    PRIMARY KEY (project_id, harness_id)
) STRICT;

CREATE TABLE setup_publication_set (
    set_digest       TEXT PRIMARY KEY,
    setup_stable_id  TEXT NOT NULL,
    setup_version    TEXT NOT NULL,
    account_id       TEXT NOT NULL,
    device_id        TEXT NOT NULL,
    members_json     TEXT NOT NULL,
    state            TEXT NOT NULL,
    created_at       TEXT NOT NULL
) STRICT;

CREATE TABLE store_port_import (
    import_key      TEXT PRIMARY KEY,
    adapter         TEXT NOT NULL,
    snapshot_digest TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    stable_id       TEXT NOT NULL REFERENCES entity(stable_id),
    revision_id     TEXT NOT NULL REFERENCES revision(revision_id),
    imported_at     TEXT NOT NULL,
    UNIQUE (adapter, snapshot_digest, external_id)
) STRICT;

CREATE TABLE sync_abandoned_event (
    account_id   TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    abandoned_at TEXT NOT NULL,
    PRIMARY KEY (account_id, event_id)
) STRICT;

CREATE TABLE sync_cursor (
    account_id TEXT PRIMARY KEY,
    cursor     TEXT,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE sync_event (
    account_id         TEXT NOT NULL,
    event_id           TEXT NOT NULL,
    sync_key           TEXT NOT NULL,
    local_revision_id  TEXT,
    remote_revision_id TEXT NOT NULL,
    entity_id          TEXT NOT NULL,
    direction          TEXT NOT NULL,
    request_json       TEXT NOT NULL,
    state              TEXT NOT NULL,
    receipt_json       TEXT,
    created_at         TEXT NOT NULL,
    PRIMARY KEY (account_id, event_id),
    UNIQUE (account_id, remote_revision_id)
) STRICT;

CREATE TABLE sync_pending_version (account_id TEXT NOT NULL, stable_id TEXT NOT NULL, version TEXT NOT NULL, passport_digest TEXT NOT NULL, revision_id TEXT NOT NULL, created_at TEXT NOT NULL, event_id TEXT NOT NULL, PRIMARY KEY (account_id, stable_id, version)) STRICT;

CREATE TABLE sync_remote_head (
    account_id         TEXT NOT NULL,
    entity_id          TEXT NOT NULL,
    remote_revision_id TEXT NOT NULL,
    PRIMARY KEY (account_id, entity_id)
) STRICT;

CREATE TABLE tech_finding (
    project_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    coordinate TEXT NOT NULL,
    context TEXT NOT NULL,
    claims TEXT NOT NULL,
    technology_id TEXT,
    review TEXT NOT NULL DEFAULT 'proposed',
    freshness TEXT NOT NULL DEFAULT 'current',
    override_technology_id TEXT,
    override_version TEXT,
    first_seen_scan TEXT NOT NULL,
    last_seen_scan TEXT NOT NULL,
    reviewed_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, scope, kind, coordinate, context)
);

CREATE TABLE tech_mapping_cache (
    organization_id TEXT NOT NULL,
    version TEXT NOT NULL,
    digest TEXT NOT NULL,
    entries TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, version)
);

CREATE TABLE tech_scan (
    scan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    complete INTEGER NOT NULL,
    stopped_by TEXT NOT NULL DEFAULT '',
    detector_version TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    created_at TEXT NOT NULL
, source_revision TEXT NOT NULL DEFAULT '');

CREATE TABLE tombstone (
    stable_id  TEXT PRIMARY KEY REFERENCES entity(stable_id),
    reason     TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE verified_provider_release (
    provider_id    TEXT NOT NULL,
    sequence       INTEGER NOT NULL,
    artifact_digest TEXT NOT NULL,
    verified_at    TEXT NOT NULL,
    PRIMARY KEY (provider_id, sequence)
) STRICT;

CREATE UNIQUE INDEX agent_task_by_idempotency_key ON agent_task(idempotency_key);

CREATE UNIQUE INDEX agent_task_open_binding
ON agent_task(harness_id, project_root, scope)
WHERE state IN ('planned', 'blocked', 'running')
  AND intent != 'inspect'
  AND harness_id != '';

CREATE INDEX consent_by_target ON consent(target);

CREATE INDEX github_observation_by_version ON github_repository_observation(stable_id, version, observation_id);

CREATE UNIQUE INDEX one_passport_per_singleton_kind
ON entity (kind) WHERE kind IN ('developer', 'device');

CREATE UNIQUE INDEX operation_event_global_sequence_uq ON operation_event(global_sequence);

CREATE INDEX preserved_setup_by_target ON preserved_setup(target_id, created_at);

CREATE INDEX proposal_by_pair ON proposal(project_id, harness_id);

CREATE INDEX revision_by_entity ON revision(stable_id);

CREATE UNIQUE INDEX setup_publication_set_open_uq ON setup_publication_set(account_id, setup_stable_id, setup_version) WHERE state != 'published';

CREATE UNIQUE INDEX sync_push_by_key ON sync_event(account_id, sync_key) WHERE direction = 'push';

CREATE INDEX tech_scan_project ON tech_scan(project_id, scope, created_at);

CREATE INDEX version_by_line ON object_version(stable_id, major, minor);

PRAGMA user_version=53;
