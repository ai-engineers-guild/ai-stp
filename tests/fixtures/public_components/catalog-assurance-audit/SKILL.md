---
name: catalog-assurance-audit
description: "Audit one published component or setup against exact harness adaptations, target-bound safety evidence, and catalog readback."
---

# catalog-assurance-audit

Use this skill when a user asks whether a published component or setup is
actually supported by a harness, whether its safety evidence is current, or
whether the catalog and UI show the same exact facts.

## Audit procedure

1. Capture the exact stable ID, version, passport digest, and owner. Never
   substitute a name or the latest version for an exact coordinate.
2. Read the published version and its target matrix. Check every published
   adaptation for the requested harness, scope, projection digest, assessment
   state, freshness, and full-auto recommendation.
3. Treat each adaptation as independent evidence. A verified row proves only
   that exact adaptation and target; it does not prove another harness, scope,
   operating system, architecture, policy, or provider profile.
4. Compare the catalog card counts with the detail matrix. The card is an
   aggregate; the matrix is the source of truth. Report missing, stale,
   failed, unsupported, and not-verified rows separately.
5. If the user asks for a UI check, open the component or setup detail and
   the catalog result. Confirm that harnesses and tags stay compact, overflow
   lists overlay their card, and expanded projection details expose readable
   evidence without inventing support.
6. Report a compact table with the exact coordinate, harness, target scope,
   implementation, assessment, freshness, recommendation, and blocking gap.

## Safety rules

- Never turn an absent adaptation into a portability claim.
- Never treat author verification or a version-wide safety score as target
  compatibility.
- Never publish a private overlay. Public multi-harness support requires a
  materialized projection, a new immutable component version, and a separate
  assessment for that exact target.
- Do not install or change a harness while auditing. Ask for a separate
  installation request after the evidence is understood.
