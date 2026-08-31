---
description: "SPEC-021: Anonymous reading of the public catalog and initial seeding of objects."
last_verified: "2026-08-25"
---

# SPEC-021: Anonymous public catalog reading and primary seeding

## Purpose

For the first time, the platform makes the public catalog anonymous and read-only: search and
listing of components and setups, accurate reading of object and version, deterministic
opaque cursor, card and detail projections, integrity check when reading and
Safely returning object bytes. At the same time, idempotent seeding is introduced
first-party objects, sufficient for Sprint-1 E2E. Publication of user-defined
objects is not introduced in this sprint.

Wire contract fixed `#71` in `schemas/v1/openapi.json` and models
`ai_stp_contracts.catalog`; this specification does not redefine it, but describes it
server behavior behind it and owns the `REQ-21xx` requirements. Mechanism
platform belongs to `ADR-0009`; trust lines - `ADR-0016`; honesty
verification - `ADR-0026` and `ADR-0032`; canonicity digest - `SPEC-015` and
`ADR-0036`; storage and its limitations - `SPEC-020`; slice frame - `ADR-0037`;
model for anonymous reading and issuing bytes - `ADR-0042`.

## Scope

Includes: six anonymous read-only routes `/v1/catalog/components` and
`/v1/catalog/setups` (listing, object card, exact version) behind
frozen contract `#71`; opaque, tamper-resistant cursor with full
stable order, limited page and one sequence for both
trust lines; projections of the card and details from the passport of the last one offered
versions; dividing the result into `authoritative` and `experimental` sections with
request-scoped consent; independent check of digest and read size;
secure release of object bytes after object and action verification; idempotent,
first-party seeding loader tied to the environment; property of inaccessibility for
listing hidden, private and draft entries.

Does not include: arbitrary user uploading and publishing; validation workers and
scanning; private objects, grants and synchronization; recommendations, ranking
and social metrics; changing general wire diagrams and `schemas/**` (owner - `#71`);
domain semantics of columns of accounts, devices and identities (`SPEC-002`); layer
storage and migrations as such (`SPEC-020`); REST ready surface
(`SPEC-017`); network hiding and `docker-compose` (`SPEC-019`).

## Terms

- `Catalog read route` is one of the six anonymous `GET` frozen routes
  contract `#71`; the catalog cannot be written through these routes.
- `Card projection` - projection `ComponentSummary` or `SetupSummary`: object fields
  without prefix and field `latest_*`, read from the passport of the last proposed
  versions; there is no object passport (`ADR-0012`).
- `Opaque cursor` — an order token that is opaque to the client; the server owns it
  content, the client only returns it verbatim.
- `Trust line split` — division of the result into sections `authoritative` and
  `experimental`, rather than mixing them (`ADR-0016`, `SPEC-006` `REQ-603`).
- `Non-enumeration` - a property in which the existence of a hidden, private or
  the draft record is not displayed either by direct ID, or by the cursor, or by the counter, or by the form
  time-dependent response, nor the key of the object in the store.
- `First-party seed` - deterministic set of guild objects, loaded
  an idempotent loader tied to the environment.
- `Object delivery` - issuing artifact bytes after checking the object and action:
  either an API-mediated stream or a short-lived limited URL (`ADR-0042`).

## Requirements

- `REQ-2101`: Six catalog routes are available anonymously and are read-only; no
  route for public publishing, upload, or catalog mutation exists in this sprint
  exists, which is confirmed by the absence of such operations in the implementation and contract.
- `REQ-2102`: Components and setups - separate resources; one search call
  addresses one view and the cursor belongs to one view; polymorphic object route
  not entered (frozen contract `#71`).
- `REQ-2103`: The projection of the card and details fills in the fields `latest_*` from the passport
  latest proposed version; each field `latest_*` corresponds to a real
  field of the passport, which is confirmed by the test; object fields `name` or `tags` card
  does not carry it, since there is no object passport (`ADR-0012`).
- `REQ-2104`: Each card carries `CatalogTrust` with independent axes
  `author_verified` and `component_verified` (`ADR-0016`); line `authoritative`
  representable only with both true axes; section `experimental` returns
  only with request-scoped consent of `include_experimental` (`SPEC-006` `REQ-603`,
  `ADR-0029`) and comes in a separate section, not mixed together.
- `REQ-2105`: The order of the result is complete and stable within one cursor
  sequences with unique tie resolver `stable_id`; cursor
  opaque, tamper-resistant, and linked to a filter and sort signature;
  a cursor that is tampered with or belongs to another filter is rejected by the typed
  mistake; the page is limited in total along both lines by the value `PAGE_SIZE_MAX`;
  pagination does not create duplicates and does not miss anything.
- `REQ-2106`: Hidden, private and draft records are not displayed for enumeration:
  a direct request by ID responds with the same `AI_STP_NOT_FOUND` as an absent one
  recording; the response does not carry a dialing counter; the response form does not indicate existence
  records with time-dependent differences; the object key is opaque and does not itself grant authority.
- `REQ-2107`: The public route represents only the published passport with
  visibility `public` and published life cycle `active`, `deprecated` or
  `blocked`; We will not present a private or draft passport on a public route and
  rejected before a response is generated.
- `REQ-2114`: Default view list only offers lifecycle
  `active`. `deprecated` and `blocked` remain fully achievable - by `id`, by
  exact version, in the list of object versions and by explicit `include_deprecated` - but
  the list is a recommendation, but the preempted version is not.
  `REQ-2107` answers whether an entry is representable and does not answer this question;
  until 2026-08-30 one set answered both, and the first page of the catalog
  consisted of nineteen displaced setups and one active one.
- `REQ-2108`: Passport bytes are checked against `passport_digest` before response, and
  artifact bytes - against digest in the `ai-stp:artifact:v1` area and size up to
  issuance; raw SHA-256 and domain digest are not interchangeable; the same
  `stable_id`/`version` cannot be associated with a conflicting digest, and such
  conflict is rejected with a typed error without partial response (`SPEC-015`,
  `ADR-0036`). The type of this error does not mean missing: reachable published
  an entry that fails verification responds with `AI_STP_CATALOG_INTEGRITY` and leaves
  level event `error`; a structurally unassembled passport is the same
  integrity error rather than an unhandled failure (`ADR-0079`). Wired field
  `passport` exact version - saved published document, according to which
  digest is considered, not re-serialization through the current model: fields,
  that appeared later with default values are not included in the historical snapshot
  are substituted. The client checks digest against this object before parsing the model.
- `REQ-2109`: **Sprint 1:** `#71` public HTTP contract **does not** contain a route
  issuing artifact bytes (decision / issue `#142`: defer). Clients only receive
  metadata and passport on six `GET` routes; `REQ-2108` still requires
  checking `passport_digest` when reading the passport. **After Sprint 1:** bytes
  artifacts are issued only after checking the object and action - API-mediated
  by stream or briefly live limited URL on `ADR-0042`; opaque key
  The object itself does not provide access to bytes (`SPEC-020` `REQ-2004`). Additive
  the route to `#71` is a separate decision of both contract owners.
- `REQ-2110`: Fixture seeding loader is idempotent and tied to the environment;
  rerunning does not create duplicate metadata lines or artifacts; everyone
  the seeded passport is schema-valid, published, and public. Environment binding
  is a refusal, not a preference: seeding runs only where the environment
  named `dev` or explicitly required `AI_STP_SEED_FIXTURES`; on any serving
  environment it is not executed at all. The reason is that fixtures are
  `fixture-component`, `river-*` and `northwind-*`, that is, invented objects, and on
  on the public site they appear alongside real objects. Catalog-integrity checking is
  separate from seeding and runs everywhere: it reads published data rather than writing.
- `REQ-2111`: API never marks the version checked beyond the saved one
  state of evidence; `component_verified` reflects only saved received
  proof (`ADR-0026`, `ADR-0032`), and not the fact that the platform launched the check.
- `REQ-2112`: The implementation passes `ai_stp_contracts.conformance.run_conformance`
  above the common body `ai_stp_contracts.fixtures` - the same one to which the moc is subordinated
  CLI; "mock conforms" and "API conform" mean the same thing.
- `REQ-2113`: CLI receives published `SetupVersion` only full exact
  closure: checks the passport and artifact of the setup, each exact reference to the component,
  passport, harness and artifact of each component, and then one local
  transaction materializes an immutable graph. The revision seal and `passport_digest`
  are checked against the published document, and not against a re-serialization of the current
  models. Offline retry does not open the network, rechecks the cache and either
  returns the same graph, or type-fails without a partial record.

## States and errors

Catalog reading completes successfully with a resource body, with a typed
`AI_STP_NOT_FOUND` error for a missing or non-public entry (indistinguishably),
with a typed invalid-request error for a violated request schema, a forged or
foreign cursor, or an unknown request field, or with a dependency-unavailable
error. An unknown request field causes rejection, not compatibility: a silently
discarded filter is a lost filter. Responses allow additional fields; requests do
not. The read-integrity check succeeds when the digest and size match and returns
a typed error on mismatch or conflict, without a partial response. Every response
carries `X-Request-Id`.

## Security and privacy

The anonymous route is the main discovery channel, so it only represents
published public passport: private passport carries the source repository,
exact commit and subpath, names of required environment variables, external addresses and
owner ID, and on a public route it's a leak. The existence of a hidden
private and draft recordings are not output by any of the listed channels
(`REQ-2106`). A gap in version numbers is not a channel: version hiding is not
frees her number (`SPEC-005`), so the loose sequence is fair
answer, not evidence. The object key is opaque and does not itself grant authority; bytes
are issued in a separate verified step. Secrets, tokens, environment values and
optional personal data is not included in passports on the public route,
logs, metrics, traces and fixtures.

## Compatibility and migration

The `#71` contract in this sprint is changed only additively and only by `#71` himself
recorded migration with the consent of both owners; divergence between issue prose and
frozen contract is resolved in favor of the contract, and the need for a new field
(for example, the card publisher or a separate route for serving bytes) is formalized as
additive application to `#71`, and not as a local deviation. Publication status
(`published_at`, trust line, verification axes) is added to the storage schema
optional - first expansion by `SPEC-020` and `docs/engineering/schema-evolution.md`,
without overriding ownership of the `SPEC-020` storage layer. Changing the digest area or
canonicalization requires a new version under `SPEC-015`.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-2101` | The test confirms anonymous success for six `GET` routes and the absence of any catalog-write route in the implementation and contract. |
| `REQ-2102` | The test confirms that the resources of components and setups are separate and that the cursor of one type is not accepted by the other. |
| `REQ-2103` | The test connects each field `latest_*` of the card with the real field of the version passport and confirms the absence of object `name`/`tags`. |
| `REQ-2104` | The test confirms the independence of the axes, the representability of `authoritative` only for both axes, and the appearance of the `experimental` section only for `include_experimental`. |
| `REQ-2105` | The Property test confirms complete stable order with the `stable_id` resolution, rejection of counterfeit and foreign cursors and the absence of duplicates and omissions during pagination. |
| `REQ-2106` | The test confirms the same `AI_STP_NOT_FOUND` for the missing and non-public record, the absence of a counter and the opacity of the object key. |
| `REQ-2107` | The test confirms the refusal to present a non-public or draft passport on a public route before generating a response. |
| `REQ-2114` | The test confirms that the default list does not contain `deprecated`, that `include_deprecated` returns them, and that a cursor released with one flag value is not accepted with another. |
| `REQ-2108` | A negative test confirms the verification of the domain artifact digest and read size, the separateness of the raw SHA-256 cache and the rejection of the conflicting digest for the same `stable_id`/`version`. A separate test confirms that the corrupted reachable record responds with `AI_STP_CATALOG_INTEGRITY` rather than none, leaves the event with a cause and identifiers, and that an unparsed passport gives the same integrity error. The exact version test confirms that the wired `passport` matches the stored document, even when the current model would substitute fields with default values, and that the client checks the digest against this object before parsing the model. |
| `REQ-2109` | Sprint 1: the test/contract confirms the **absence** of a public route issuing artifact bytes and that the `object_location` key is not an authority. After introducing route, the issuance test is performed only after checking the object and action. |
| `REQ-2110` | The test confirms idempotent reseeding without duplicates, passport validity and public status, and an entirely experimental seeded trust line; a separate test confirms that a named serving environment receives no fixtures, an unnamed environment is treated as development, and the explicit requirement resolves in both directions. |
| `REQ-2111` | The test confirms that the API does not mark the version verified beyond the stored evidence state. |
| `REQ-2112` | The `run_conformance` run over the common fixture body completes with no findings for the API implementation. |
| `REQ-2113` | Client tests receive the exact setup graph, collect it from the local registry, repeat the acquisition without a network and confirm idempotency; a corrupted cache is rejected, and a failure within a transaction leaves no partial graph. A separate test confirms that a passport without later added fields with default values ​​passes acquire if the revision seal matches the published document. |
