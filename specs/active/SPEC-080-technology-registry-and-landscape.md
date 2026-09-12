---
description: "SPEC-080: Governed technology metadata, usage facts, detection handoff, and authorized landscape projections."
last_verified: "2026-09-12"
---

# SPEC-080: Technology registry and landscape

## Purpose

Implement issue #207 without duplicating the relationships owned by #209.
Manual declarations and governance remain usable without detectors or forge APIs.

## Scope

This specification owns technology/category metadata, aliases, lifecycle,
coordinate mappings, usage evidence and review semantics, and landscape projections.
SPEC-081 owns all team/project/technology links and responsibility. A technology
usage is evidence and a review decision attached to SPEC-081's single canonical
project–technology relation, not a second independently editable relationship.
Detector execution and forge enrichment remain #222/#208 responsibilities.

## Terms

- `Technology` — a concrete software language, library, framework, runtime, API,
  standard, product, tool, or infrastructure service.
- `Category` — a governed classification, never a technology or component kind.
- `Usage fact` — version, context, evidence, review, and freshness metadata on a
  canonical project–technology relation.
- `Subject reference` — what an object discusses or addresses; never proof of use.
- `Landscape` — a read projection over authorized canonical relations and facts.

## Requirements

- `REQ-8001`: Registry records have stable technology/category identifiers,
  canonical names, descriptions, category references, aliases, optional icon and
  official reference URLs, lifecycle, revision, and safe provenance. Changes to
  names/categories never replace identifiers. Canonical metadata is separate from
  organizational adoption and responsibility decisions owned by SPEC-081.
  Records are resolved within an explicit organization namespace. Imported seed
  technology/category IDs and provenance remain stable across replay; tenant edits
  do not alter another tenant's metadata. Typed IDs use the `technology` and
  `category` prefixes, not passport object-kind or harness namespaces (ADR-0181).
- `REQ-8002`: Seed/import replay preserves identifiers and manual edits. Initial
  categories cover language, library, framework, runtime, browser, Web API/standard,
  DBMS, cache/key-value store, broker/event platform, build/bundling, package manager,
  artifact registry, test framework, test runner/browser automation, CI/CD,
  execution agent, containers/orchestration, OS, cloud/managed services, Web server/
  proxy, provisioning/configuration, observability, and identity/security.
  `harness`, `setup`, `component`, `mcp`, `skill`, `hook`, `agent`, `plugin`, and
  `command` are not categories. Bun is one technology with multiple categories;
  npm CLI/registry and GitLab CI/CD/Runner are separate identities.
- `REQ-8003`: Alias resolution normalizes Unicode NFKC, case, and whitespace;
  punctuation is not silently deleted. Explicit React.js and Postgres aliases
  resolve to React and PostgreSQL. Collisions return a stable conflict and
  ambiguous candidate matches require explicit selection. Ordinary edits cannot
  merge identities. Deliberate merge preserves the source ID as a redirect,
  canonical references, original evidence, and audit history; conflicting facts
  or organizational decisions abort until explicitly resolved.
- `REQ-8004`: Technology lifecycle is `draft`, `active`, `deprecated`, `archived`.
  Only explicitly authorized maintainers approve draft→active. Draft→archived,
  active→deprecated/archived, deprecated→active/archived, and restoration to the
  retained pre-archive state are supported. Archiving a never-approved draft does
  not make it approved on restoration. Deprecated entries discourage new use;
  archived entries are absent from default new-use choices. Existing uses survive.
- `REQ-8005`: Coordinate mappings are immutable versioned records connecting
  package/image/executable/configuration coordinates to canonical technologies,
  with mapping version and provenance. A coordinate, version, hosted instance, or
  component is not automatically a technology. Refreshes propose changes and
  never rewrite reviewed historical facts or approved governance metadata.
- `REQ-8006`: Authorized users manually declare, confirm, reject, override,
  correct, and retire usage facts through API and Web. Review states are proposed,
  confirmed, rejected, overridden, and retired, independent of technology lifecycle.
  An authorized manual declaration is confirmed without requiring a scan.
  Unknown version, declared range, and observed version remain distinct.
  Contexts distinguish production, development/build, testing, and browser support.
- `REQ-8007`: Evidence records preserve safe source/reference, repository-relative
  path where applicable, observed time, source revision, confidence, detector and
  mapping versions. Evidence freshness is separate from review. Repeated scans
  preserve owner confirmation, rejection, and overrides; conflicting observations
  are disagreements, not silent replacements. Only a complete scan of the same
  scope can mark earlier observations absent; incomplete scans indicate uncertainty.
- `REQ-8008`: The versioned #222/#208 handoff names canonical technology identity,
  stable local project ID, explicitly linked remote project ID and organization
  where publication applies, scan scope/completeness, detector/mapping version,
  source revision, and safe evidence. Publication is idempotent and currently
  authorized; detectors never infer or alter ProjectLink. Harness/setup/component
  observations remain their own domains. Proposed technology observations cannot
  silently become approved usage or organizational adoption policy.
- `REQ-8009`: Organization/team/project table and category-grouped views share
  one query contract with name/alias, category, technology lifecycle, usage context,
  review, freshness, project lifecycle/activity, team, and project filters. Counts
  are distinct authorized remote projects per technology after filtering, not
  evidence/version/team-membership counts. Grouping and drill-down preserve that
  unit and explain active filters. Subject/applicability references do not count.
  Confirmed/overridden current uses are default; proposals are separately visible.
- `REQ-8010`: Active totals exclude archived, deprecated, deleted, and inactive
  projects by default. Repository inactivity defaults to more than nine calendar
  months and has an organization-configurable threshold and authorized explicit
  override. Missing activity is unknown, not inactive. Project activity and
  technology lifecycle/adoption are separate. Historical filters retain references
  and safe evidence, distinguishing no known use, not scanned, stale/incomplete
  evidence, and unavailable source. Radar adoption requires explicit organization
  decisions; radar/relationship views cannot introduce different count semantics.
- `REQ-8011`: CRUD, resolution/search, evidence, counts and drill-down enforce
  current independent list/read/mutation permissions before aggregation. Tenant
  scope and composite relationship constraints prevent foreign references.
  Revision preconditions and tenant-scoped fingerprinted idempotency prevent
  partial edits, merges, and duplicate decisions. Audits include safe before/after,
  actor, source, reason, request correlation and time for governance, denial and
  replay. Any introduced job reauthorizes at execution; any cache/export/search
  projection uses the same tenant and authorized-resource partition.

## States and errors

### Landscape wire contract

`GET /v1/corporate/organizations/{organization_id}/technology-landscape` accepts
optional category, technology, project and team IDs; lifecycle, adoption, usage
context, review and freshness filters; `include_history`, `include_inactive`, and
bounded `offset`/`limit`. Omitted review selects confirmed/overridden uses and
omitted freshness excludes absent facts. Project inactivity compares repository
activity against a UTC calendar-month cutoff, clipping the day at month end;
activity exactly at the cutoff remains active. Explicit activity overrides take
precedence; missing activity remains unknown.

The response carries applied filters, evaluation time, inactivity threshold,
authorized technology rows, and an authorized pre-pagination technology total.
Each row carries technology metadata, distinct project count, a separate proposed
project count, and bounded project drill-down entries with names, canonical IDs,
activity and matching usage facts. Drill-down pagination is independent of row
pagination and retains the row's full distinct count. Grouped, radar and relation
views consume this same response and retain filter parameters in navigation.

Registry lifecycle, usage review, evidence freshness, project lifecycle/activity,
and data-source availability are independent dimensions. Use existing corporate
`capability_forbidden`, `capability_stale`, `revision_conflict`, and
`contract_invalid` conventions. Registry-specific reasons distinguish invalid
category, duplicate identity, alias conflict/ambiguity, merge conflict, archived
new-use target, and unavailable evidence. Unknown and foreign protected IDs have
the same non-enumerating response. Web preserves drafts and offers refresh or
explicit conflict resolution without silently retrying a different effect.

## Security and privacy

Store safe bounded metadata and references only: no secrets, credentials, source
contents, absolute local paths, or unnecessary personal data. Reference URLs and
evidence paths are validated at trust boundaries. Registry operations do not
execute repository code, fetch arbitrary evidence URLs, or install dependencies.

## Compatibility and migration

Publish additive storage and composite constraints before routes. Seed/import is
repeatable and cannot replace manual decisions. Preserve existing project IDs,
links, assignments and audit history; SPEC-081 defines identity integration.
Regenerate schemas/OpenAPI/Web client and documentation from source. Deploy
migrations, API, then Web. Rollback disables new surfaces/reverts application
commits while retaining identities, relations, evidence and audit rows; destructive
downgrade requires a verified backup and is not an ordinary rollback.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8001` | Storage/API rename and reclassification tests preserve IDs and references. |
| `REQ-8002` | All category-family fixtures, reserved-kind rejection, Bun and naming distinctions; seed replay preserves owner edits. |
| `REQ-8003` | Normalization, ambiguity, collision and merge tests preserve redirects/history and abort conflicting merges atomically. |
| `REQ-8004` | Authorized/denied lifecycle transition and restoration matrix across API/Web. |
| `REQ-8005` | Versioned mapping refresh tests leave reviewed evidence and decisions unchanged. |
| `REQ-8006` | API/Web manual review matrix covers all states, contexts, unknown versions and ranges. |
| `REQ-8007` | Complete/incomplete repeated-scan and disagreement fixtures preserve owner review and immutable evidence. |
| `REQ-8008` | Detector handoff contract fixtures reject private data, implicit links and component-as-technology publication. |
| `REQ-8009` | Shared-filter table/grouped/drill-down tests count distinct authorized projects despite duplicate evidence and multiple teams. |
| `REQ-8010` | Deterministic activity-threshold/override/unknown/history/source-state and adoption-policy tests. |
| `REQ-8011` | Hostile tenant/scope, concurrent revision, idempotency, audit and every introduced infrastructure-surface test. |
