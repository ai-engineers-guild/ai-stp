---
description: "Machine contract for shared descriptors used by local ports and metadata adapters."
last_verified: "2026-08-16"
---

# Federated sources

## Shared boundary

`FederatedSourceDescriptor` version `federated-source/1` projects an external
source without importing its vendor schema into the passport.
`source_kind=local_port` denotes an exact local snapshot; `metadata_adapter`
denotes an official remote observation. Both kinds have
`authority=external_observation`, false verification axes, and
`target_write=false`.

The fields and closed vocabulary belong to the generated
`federated-source-descriptor` schema. `FederatedSourceSet` stores multiple
references for one ASTP object and records `auto_merged=false`.

## Identity and deduplication

The dedup key is the exact provider/external identifier pair. For SX/APM, the
external identifier is the snapshot digest. For an available GitHub observation,
it is the immutable repository id; before the first successful observation, it
is the exact source coordinate. A similar name and observed metrics from another
provider are not an exact identity match.

## Authority

A local port may declare only `confirmed_private_draft_import`: the actual import
remains a separate digest-bound operation requiring confirmation. A metadata
adapter has `registry_effect=none`. No descriptor publishes an object or changes
eligibility, verification, lifecycle, or the target.

## Freshness and extension

A local snapshot has `local_snapshot`, records `checked_at`, and does not invent
a network fetch time. A remote observation is `fresh`, `stale`, or `unavailable`;
only unavailable omits `fetched_at`. `external_state` carries `present`,
`archived`, or `unavailable` as an observation, not an ASTP lifecycle decision.
A local port has no network rate limit; a metadata adapter must follow its own
TTL and rate-limit policy. Adding a `provider` or `source_kind` changes the
closed contract and requires a specification, schema generation, and a
validation fixture.

## Catalog metadata adapters

Server-owned adapters have provider `skills_sh`, `nori`, or
`modelcontextprotocol`. The exact coordinate is set before fetch and contains the
provider and its immutable external identifier; a response cannot associate
itself with an ASTP object. One object stores multiple such descriptors.

The observation allowlist is `display_name`, `summary`, `homepage_url`,
`repository_url`, `published_at`, `updated_at`, `popularity_count`, and
`external_state`. Fields are optional and bounded; unknown fields are discarded
before persistence. The descriptor separately stores the source URL,
attribution, terms URL, `fetched_at`, `checked_at`, `expires_at`, and freshness.
Artifact content, executable snippets, verification, trust, and install claims
are excluded.

Shared upper bounds: `256 KiB` response, JSON depth `16`, `100` collection
elements, `4096` Unicode code points per string, `8` references per revision,
connect timeout `2 s`, read timeout `5 s`, cache of `1000` entries per provider,
and TTL `6 h`. The fetch limit is at most `60` requests per minute per provider
and never exceeds the source's published limit. A stricter provider policy
always takes precedence.
