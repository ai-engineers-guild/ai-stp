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
  Technology mutations accept SPEC-076's opaque corporate authorization revision;
  legacy integer policy counters remain accepted for compatibility. Both are
  checked under the tenant mutation lock; opaque revisions bind the organization
  and membership revision and are never parsed by Web.

## States and errors

Project lifecycle is owned by SPEC-079 and ADR-0182. Landscape filters use its
authoritative active/deprecated/archived/deleted lifecycle, not the legacy
active/archive compatibility projection. Historical drill-down retains exact
project IDs and tombstoned metadata under current independent read permissions.

### Initial registry import

`POST /v1/corporate/organizations/{organization_id}/technology-seed` imports the
fixed seed version `1`, using a fingerprinted idempotency key, current corporate
authorization revision and `expected_revision: 0`. It requires independent
organization-wide `category.create` and `technology.create` permissions. The
response names created and retained seed IDs, without disclosing other records.
All 23 category families and Bun, npm CLI, npm registry, GitLab CI/CD, GitLab
Runner, React and PostgreSQL have fixed manifest IDs. Bun includes runtime,
package-manager, build and test-runner classifications. React.js and Postgres are
explicit aliases. Imported technologies start as drafts; importing is not approval.
Existing manifest IDs retain all metadata, classifications, aliases, revisions,
lifecycle and decisions. A colliding non-manifest identity aborts the transaction.
Import is manually available in Web and does not depend on detection.

### Deliberate merge preservation

A deliberate merge names source and target technology IDs and both record
revisions under the current tenant authorization revision. It requires explicit
merge and read permissions for both technologies and the independent scoped
mutation permissions for any canonical links or organizational decisions changed.
The target cannot already be a redirect. Neither an ordinary edit nor a search
can initiate a merge.

`GET /v1/corporate/organizations/{organization_id}/technologies/{source_id}/merge-plan`
with a typed `target_id` performs current authorization and conflict preflight
without structural mutation. It returns authorized source/target metadata,
affected distinct project/team counts and a canonical `ai-stp:plan:v1` digest
including the merge kind, tenant, revisions, links, facts and decisions.
`POST` on the source's `/merge` path requires that exact digest and both
technology revisions. The server recomputes the plan under the tenant mutation
lock and rejects any changed input. Replay still reauthorizes every affected
scope; a preview is never authority.
The merge response records retained source/target views and per-project/team
effects, including the canonical relation IDs and the originally authorized
target create/update action. This immutable effect report is not another link
model. Receipt replay checks those original mutation requirements against the
current policy; it never treats the report as a stored authorization decision.

A retained target pair intentionally retired by an owner is a merge conflict,
not permission to reactivate it. Creating a new current target project pair
requires an active target technology. Organizational decisions are retained;
non-default source and target decisions must already agree, otherwise the owner
must explicitly resolve them before merging. Merge never copies approval or
adoption into an undecided target.

Retain the source technology as an archived redirect and retain its original
canonical relation IDs, facts and evidence as retired history. Existing relation
endpoints are immutable: create a target canonical pair only if absent, otherwise
reuse its ID. Compatible facts can combine safe deduplicated evidence within
contract bounds; conflicting context/version/review/freshness or organizational
decisions abort the entire merge before structural mutation. Target canonical
name, description, lifecycle and approval are not silently replaced by the source.
Combine classifications and transfer lookup aliases without losing audited source
metadata. Immutable mapping and scan records retain original IDs and resolve
through the retained redirect when producing current projections. Current counts
include only the target canonical pair once; historical source references remain
resolvable. Replay reauthorizes and returns the same result without a second merge.

### Detector publication and mapping snapshots

`PUT /v1/corporate/organizations/{organization_id}/technology-mappings/{version}`
publishes one immutable, digest-addressed mapping snapshot. Creation uses expected
revision zero, organization `technology.update`, and independent read/update
permissions for each named technology. Reusing a version with different content
is a conflict, even with a different idempotency key. Reads require organization
`technology.list` and independent read permission for every snapshot entry; a
partial snapshot is never presented as the complete mapping version.

`POST /v1/corporate/organizations/{organization_id}/projects/{project_id}/technology-scans`
accepts the version-1 handoff, exact project revision and current authorization.
The public `technology.scan_publish` capability maps to the existing domain
permission `technology.scan.publish`; this is one permission, not an alternate
grant. Independent project read and canonical pair create/update permissions are
required. Publication requires exact matching organization/remote project IDs,
an active project, a published mapping version and safe evidence with matching
detector/mapping versions. Local IDs are descriptive and never create ProjectLink.
Unknown or foreign technology endpoints abort before any write. Immutable scans
retain original technology IDs; current projections follow authorized redirects.

Each technology/context occurs at most once in a handoff. New observations create
only proposed facts on the canonical pair. Reviewed or retired facts and their
versions/evidence are never overwritten. Differences are returned as explicit
disagreements and remain in immutable scan history. Repeated identical observations
can refresh freshness without changing owner review.
Conflicting complete observations mark detector-only owner evidence stale;
incomplete conflicts mark it unknown. Manual evidence retains its independent
freshness. Detector-reported observed versions require actual observed evidence;
a forge-language signal alone cannot claim an observed software version.
Only observations previously published in the same scope are eligible for absent/unknown refresh: complete
omission means absent, incomplete omission means unknown. Manual-only facts and
facts covered by another scope are unaffected. Intentionally retired pairs are
not reactivated. Scan IDs are tenant-unique and fingerprinted; identical replay
reauthorizes current scopes and returns the same effect, changed content conflicts.
Publication increments the project revision atomically once; any preflight failure
leaves scans, canonical pairs, owner facts and revisions untouched.
Known-ID `GET` on the project's `/technology-scans/{scan_id}` path exposes the
immutable handoff and effect/disagreement report under independent project,
canonical-pair and original/current technology read permissions. Historical
reads remain available for retained archived/deleted project identities.

### Landscape query and projection

Organization activity policy is read through
`GET /v1/corporate/organizations/{organization_id}/technology-landscape-policy`
under `landscape.read`, and updated through `PUT` on that path under independent
`landscape.manage`. A missing policy projects to nine months and revision zero;
creation requires expected revision zero, subsequent updates the exact revision.
The threshold is 1–120 calendar months. Mutations use current authorization,
tenant-fingerprinted receipts and safe before/after audit.

`PUT /v1/corporate/organizations/{organization_id}/projects/{project_id}/activity`
requires scoped `project.update`, the exact project revision and current
authorization. It sets a safe UTC repository activity timestamp (or explicitly
unknown) and an independent active/inactive override (or clears the override).
It never changes project lifecycle or introduces a forge credential. Deleted
projects reject this mutation until explicit restoration. Reads retain activity
metadata under scoped `project.read`; override always wins over the timestamp.

Registry and landscape requests accept bounded `query` text (1–200 characters,
not whitespace-only), matching normalized canonical names and explicit aliases
as literal substrings. Search returns authorized candidates, never silently
selects or merges an ambiguous identity. Filtering happens before totals and
pagination; punctuation retains meaning and SQL wildcard characters are literal.

Known-identity technology views expose `restore_lifecycle`, the retained state
used by archive restoration. Web pins the loaded record revision for edits and
lifecycle changes; capability refresh does not silently rebase an unsaved draft.
Restoring an archived draft uses `technology.update`, not approval; restoration
to active remains guarded by `technology.approve`.
Known-ID `GET` on `/projects/{project_id}/technologies/{technology_id}` reads the
canonical pair and facts under independent project, technology and canonical-pair
read permissions without requiring list permission. Web explicitly loads that
snapshot for review, pins its revision, and preserves safe evidence across owner
decisions; a capability refresh never rebases the loaded draft.

`GET /v1/corporate/organizations/{organization_id}/technology-landscape` accepts
optional category, technology, project and team IDs; technology lifecycle,
canonical `project_lifecycle`, `activity`, adoption, usage
context, review and freshness filters; `include_history`, `include_inactive`, and
bounded `offset`/`limit`. Omitted review selects confirmed/overridden uses and
omitted freshness excludes absent facts. Project inactivity compares repository
activity against a UTC calendar-month cutoff, clipping the day at month end;
activity exactly at the cutoff remains active. Explicit activity overrides take
precedence; missing activity remains unknown.
Selecting a non-active project lifecycle is explicit historical selection and
requires `include_history`; otherwise the historical project set is empty.
The `view` parameter selects table, grouped, radar or relationships presentation
without changing filtering, authorization, count units or pagination. Each row
optionally exposes the canonical organizational decision under independent
`technology_decision.read`; null is not permission to infer approval/adoption.
Radar places a technology only from an explicit readable adoption decision;
otherwise its placement is unavailable/undecided. Multi-category grouping repeats
the same technology row in its categories, not another use or additive total.

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

## Retained category removal

Category deletion archives the same category identity under `category.delete`;
it never deletes classifications or allows seed replay to recreate owner-removed
entries. Categories have active/archived state, independent of technology lifecycle.
Known-ID reads retain archived metadata under current permissions. Dictionary
management lists include retained entries with explicit state; new classifications
require active categories. Existing classifications survive archival and metadata
edits may retain their already assigned archived categories, but cannot newly
assign an archived category. Restoration uses `category.update` with the exact
loaded category revision, current authorization and an idempotent effect.
Ordinary metadata changes cannot restore an archived category. Names remain
reserved while archived to prevent another identity from occupying the same
lookup. Archive/restore preserve category IDs, audit before/after and revisions;
replay reauthorizes the original action without a second state change.

## Independent repository source availability

Corporate projects retain an explicit source-availability signal: unknown,
available or unavailable. It is independent of project lifecycle, repository
activity, usage review and scan freshness. Missing activity, no scan, an absent
dependency and an archived project do not infer source unavailability. New and
backfilled projects start unknown. The existing revision-guarded project activity
representation may explicitly update this signal under `project.update`; an
omitted additive request field preserves it for older writers. Read projections
expose it under the same exact project read authority and the landscape filters
by it before distinct project counting and pagination. Manual confirmed facts
remain usable and countable even when their repository source is unavailable.
Changing source availability does not alter lifecycle, facts, scans or decisions.
Rollback retains this additive column and its safe audit history.

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
