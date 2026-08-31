---
description: "Decision to use X.Y versions and major-line access."
last_verified: "2026-08-03"
---

# ADR-0004: Use X.Y versions and major-line access

Accepted on 2026-08-03.

## Context

A setup pins exact component versions, while installation is addressed by digest. A floating version or reused number would make installation irreproducible and invalidate verification evidence tied to an exact hash. At the same time, a future paid-access boundary is needed that does not break already installed setups.

## Decision

A Setup/Component version has the `X.Y` format and immutable content. A minor belongs to the same major line. Any change to exact component refs creates a new setup version. A major is created only after an explicit user decision and is a future access boundary.

## Consequences

The version is stored as a string but compared as two non-negative integers. A minor increment is computed automatically; a major line is created only by user decision. A published version number is never reused under any circumstances, and a correction is released as a new version. The major line becomes the unit of future paid access.
