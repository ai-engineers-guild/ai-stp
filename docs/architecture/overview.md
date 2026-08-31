---
description: "Overall data flow and the boundaries of the local and server environments."
last_verified: "2026-08-04"
---

# Architecture Overview

## One Product, Two Environments

### Local Environment

- CLI;
- Agent Skill;
- local registry;
- project index;
- setup compiler;
- validation runner;
- provider client;
- operation journal.

### Server Environment

- FastAPI;
- PostgreSQL;
- worker;
- RustFS/S3;
- OAuth;
- Next.js;
- Resend.

Both environments use the same schemas and terms, but do not have to share a runtime package.

## Main Flow

```text
Developer Passport
+ Project Passport
+ selected harness
+ local and cloud candidates
        ↓
hard filters
        ↓
Agent asks questions and creates composition proposals
        ↓
user confirmation records a private SetupVersion
        ↓
Setup Graph
        ↓
deterministic Setup Compiler
        ↓
Harness Bundle
        ↓
provider plan
        ↓
backup / apply / launch / status / restore
```

## Ownership Chain

```text
Agent
  interprets findings, asks questions, and creates composition proposals

CLI and core
  discover facts, validate machine data, store the local registry,
  filter candidates, deterministically build and validate packages,
  and invoke the provider

Provider
  owns the harness program, native target, locks, backups,
  application, launch, state, and restoration

Server and catalog
  own accounts, public and private metadata, publication,
  validation policy, object lifecycle, synchronization,
  permissions, reports, moderation, and audit
```

Each layer accepts the result of the previous one and does not redo its work. The Agent is neither a policy mechanism nor a state writer; the server does not write the local target.

## Final-State Owner

`ai_stp` does not write native harness files directly. The only writer is the public provider for that harness.

## Trust

The Agent makes judgment-based decisions only after mechanical constraints have been applied. A device signature confirms a report's provenance but does not turn local execution into platform-executed validation.

## Active Target

A new setup is applied to a separate target. The current session continues to use the old one. Switching occurs only after the new target has been verified.
