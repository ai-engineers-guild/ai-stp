---
description: "Proposed requirements for People and Access pages and explainable corporate authorization."
last_verified: "2026-09-29"
---

# SPEC-096: Corporate access administration (proposal)

Status: proposed; ADR-0179 and current active specs govern shipped behavior.

## Goal

An authorized administrator can inspect people, supported actions, roles,
assignments, and effective access; make a bounded change; and see its exact
effect without exposing another tenant or granting more than allowed.

## Boundaries

Four Human pages: Members & Invitations, Access model, Roles, Employee access.
Reuse the canonical employee directory, membership, roles, bindings, invitations,
audit, and evaluator. No policy language, personal deny, generic checkbox grid
for unsupported actions, or duplicate employee identity.

## Requirements and oracles

| ID | Target behavior | Executable oracle |
| --- | --- | --- |
| `REQ-9601` | Members and Invitations are separate URL-backed tabs over the existing employee/invitation records; no-email accounts use stable IDs. | Directory, query, and no-email browser/API tests. |
| `REQ-9602` | Outstanding invitations include only unexpired pending/email-confirm-pending records; accepted/revoked/expired remain history. Name/email validation matches the real invitation contract; TTL choices use the server-supported `ttl_seconds` contract. | State/count and form/API parity tests. |
| `REQ-9603` | Invitation, employee, role, parent-role and binding changes use one server delegation bound, including inherited rights and acceptance-time recheck. | Negative forged-request matrix with `lead` attempting superadmin and stronger custom roles. |
| `REQ-9604` | Access model lists only enforced actions, supported scopes, preconditions and page/data/operation distinctions; unsupported differs from forbidden and state-blocked. | Descriptor-to-handler coverage check and screen state assertions. |
| `REQ-9605` | Roles distinguish immutable system definitions, custom own permissions, inherited sources and scoped assignments; parent cycles fail before write. | Role-cycle/immutable-role integration tests and editor UI tests. |
| `REQ-9606` | Employee access shows independent role bindings, personal allows, private grants and effective decisions for a selected scope; no invented Full/Extended/Standard authority tier. | Multiple-source and scoped explain browser/API tests. |
| `REQ-9607` | Explain cites only sources granting each action, with binding/grant ID and role/scope path; single and bulk decisions agree. | Seed two disjoint roles and compare source sets and decisions. |
| `REQ-9608` | Membership synchronization mutates only its own origin bindings; revoking one source retains remaining effective access. | Independent-binding and multi-source revocation transactions. |
| `REQ-9609` | Explicit organization coverage and create-parent checks replace role-name propagation without silently changing legacy effects. | Staff create-only, superadmin/custom equivalence and migration before/after matrix. |
| `REQ-9610` | No mutation can remove the last effective active organization superadmin; unrelated edits remain permitted. | Concurrent demote/suspend/scope/delete negative and positive matrix. |
| `REQ-9611` | All protected lists, counts, exports, row actions and explain responses filter foreign-tenant data before pagination and enrichment. | Cross-tenant hostile IDs and side-channel integration tests. |
| `REQ-9612` | Mutation preview shows safe before/after, affected bindings and current revision; stale revisions fail without silent overwrite; audit reflects committed effects and denials. | Conflict/replay/audit transaction tests and form recovery tests. |

## States and errors

Each page handles loading, forbidden, empty, partial data, network error,
stale revision, successful mutation, and interrupted form. A denied action
must not be presented as an empty result. Invitation tokens appear only in
the creation receipt and never in list/export or audit payloads.

## Security and migration

Server reauthorizes every operation. Descriptor rollout precedes controls.
Legacy origin/coverage is backfilled only from provable relationships; uncertain
rows require review. Default-role changes require a separate before/after
preview and migration. Generated schemas/client follow source contracts.
