---
type: article
slug: safe-setup
locale: en
title: Build a setup without hiding its trust boundary
description: A practical guide to provenance, exact versions and explicit consent in ai_stp.
published_at: 2026-08-12
tags: [trust, setup]
draft: false
---

An ai_stp setup pins exact component versions and keeps provenance visible. Mechanical compatibility and safety checks run before agent reasoning.

![A visible trust boundary around a pinned setup](/content/illustrations/trust-boundary.svg)

## Keep the boundary explicit

- Treat author verification and component verification as independent facts.
- Require explicit consent before selecting experimental objects.
- Let only the public provider write the final harness state.

## Read the evidence in order

Start with origin, then verification, then compatibility. A verified author does not automatically make every component verified, and a compatible component does not grant permission to install it.

## Stop safely

When a policy check fails, keep the exact version and evidence visible. Do not silently swap a dependency or widen consent: return a refusal that tells the operator which boundary stopped the plan.
