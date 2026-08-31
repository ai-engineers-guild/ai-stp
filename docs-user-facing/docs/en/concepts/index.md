---
title: "Concepts"
description: "The ai_stp concepts a user and an agent need."
---

# Concepts

## Harness

A harness is the CLI environment a coding agent runs in. In the MVP, Claude
Code, Codex and Grok Build have primary support; Pi and OpenCode are beta.

More: [supported harnesses](../harnesses.md).

## Setup

A setup is the complete configuration of one harness. It belongs to that
harness from the moment it is created, and it pins exact component versions.

Any change to what it contains produces a new version of the setup.

## Component

A component is one part of a setup, of one of these kinds:

- `instruction`;
- `skill`;
- `mcp`;
- `hook`;
- `command`;
- `agent`;
- `plugin`;
- `setting`.

Memory, rules, parameters and helper tools are the *content* of an
`instruction`, a `skill` or a `setting` — not kinds of their own.

More: [component kinds](../components/index.md).

## Passport

A passport is a versioned, machine-readable description of an object. Through
passports, `ai_stp` ties together provenance, compatibility, constraints and
check results.

## Trust line

The trust line decides how an object reaches a result set:

- `authoritative`;
- `experimental`;
- `local_owner_or_pinned`.

An unverified object takes no part in automatic installation without the
user's explicit consent.
