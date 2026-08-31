---
type: article
slug: compatibility-gates
locale: en
title: Compatibility is a gate, not a suggestion
description: See how exact versions, harness support and policy checks turn a proposed setup into a deterministic plan or a useful refusal.
published_at: 2026-08-12
tags: [compatibility, setup, policy]
draft: false
---

A useful setup is more than a list of attractive components. Every pinned version must fit the target harness, platform and trust policy before a provider can apply it.

![Compatibility signals converging on one deterministic decision](/content/illustrations/compatibility-gate.svg)

## Start with exact inputs

The builder receives exact component versions and a concrete target. It does not silently upgrade, replace or reinterpret them while checking the graph.

## Separate the gates

- Schema and dependency constraints decide whether the graph is structurally valid.
- Harness and platform support decide whether the target can execute it.
- Trust and consent policy decide whether the operation is permitted.

## Make refusal actionable

A failed gate should identify the incompatible edge or missing consent. The operator can then change the proposed plan explicitly instead of discovering an implicit substitution after installation.
