---
description: "ADR-0189: Independent tenant presentation and technology owner edit authority."
last_verified: "2026-09-18"
---

# ADR-0189: Corporate entity profile authority

## Status

Accepted. Supplemented by ADR-0192; employee presentation remains membership content
on the account-backed corporate employee projection.

## Context

Corporate Hub needs rich entity presentation and technology owners independent
of responsible leads and authors. Broad team lead presentation edits must not
broaden access administration or registry governance.

## Decision

Persist shared presentation fields and an independent profile revision on incumbent
tenant entities. Persist technology ownership as a nullable tenant-composite
membership reference. Apply separate presentation edit authorization after active
tenant membership checks and again under the incumbent organization mutation lock.
Organization administrators and leads of active teams edit any tenant presentation;
technology owners edit their own technology presentation but cannot transfer ownership.
Retain existing mutation receipts, fingerprints, authorization revision checks and
audit handling. Do not add role bindings or change legacy mutation permissions.

## Consequences

Legacy contracts remain compatible. Frontend loaders fetch one shared profile and
use its current edit capability; writes use its revision rather than legacy entity
revisions. Migration is additive; application rollback retains all new data.
SPEC-084 owns wire behavior. Gallery uploads reuse processed asset records and
byte delivery, with incumbent media validation and bounded video normalization.
Read views render owner and presentation facts without embedding mutation controls;
authorized editing is entered through the shared available-action policy in SPEC-086.
