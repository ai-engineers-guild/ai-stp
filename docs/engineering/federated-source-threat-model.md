---
description: "Threat model for federated local ports and metadata adapters."
last_verified: "2026-08-16"
---

# Federated Source Threat Model

## Protected boundaries

The canonical passport, both verification axes, immutable artifact bytes, the
local registry, and the final target do not belong to the external source. A
local port reads only an explicitly named snapshot; a metadata adapter returns
only an allowlist of observations. Installation follows the normal
selection/compiler/provider lifecycle.

## Threats and mechanical responses

| Threat | Response |
|---|---|
| Poisoned metadata | closed schema, bounded body/records, safe parser, no execution or copying of artifact bytes |
| Identity collision | only an exact provider/external id matches; a different name or URL does not create a merge |
| Source takeover | immutable external id is bound by the first observation; an identity change is closed as a conflict |
| Stale or outage | a dated snapshot is marked stale/unavailable and does not delete a passport or another reference |
| Substitution of popularity for trust | the descriptor mechanically fixes both verification axes to false and authority to external observation |
| Writing another party's state | target write is always false; local import requires a separate digest and confirmation and creates only a private draft |
| Local data leakage | the descriptor excludes path, secret, environment value, content, and device identity |
| Dependency capture | SX, APM, and remote catalogs remain optional adapters rather than runtime dependencies of the core |

## Residual risk

Attribution and freshness allow the consumer to assess an observation but do
not prove the truth of external text. The terms of use, rate limits, and
production load of each remote catalog are reviewed before enablement.
Production enablement remains closed until attribution, the terms-of-use URL,
and an approving policy decision have been recorded. The normative requirement belongs to
`SPEC-050` `REQ-5007`.
