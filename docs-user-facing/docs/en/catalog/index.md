---
title: "Catalog"
description: "How to read the public ai_stp catalog and what its results mean."
---

# Catalog

The public catalog helps you find setups and components by harness, tags,
compatibility, update date and trust line. Both mode lists setups first and
components after; each group keeps the sort you chose.

## Anonymous reading

The public catalog can be read without an account. That matters for a first
look, for local selection, and for an agent working before sign-in.

```bash
ai-stp registry search --json
ai-stp registry show <stable_id> --json
```

## What to look at in a result

Before choosing an object, check:

- the harness and the supported version;
- the exact version of the object;
- provenance and the source commit;
- `author_verified` and `component_verified`;
- the trust line;
- compatibility constraints;
- the result of the last check.

`author_verified` and `component_verified` are independent. A confirmed author
is not proof that a particular version is safe.

| Field | What it answers | Red flag |
| --- | --- | --- |
| Harness | where the object may be applied | your harness is not in the list |
| Version | which immutable version you picked | the version is not pinned exactly |
| Source | where the object came from | no commit or path, or murky provenance |
| Trust line | why the object is in the result set | `experimental` without deliberate consent |
| Verification | what the platform confirmed | only the author is verified, not the component |
| Compatibility | which constraints apply | a beta harness with no manual check |

=== "Setup"
    In a setup, what matters is the whole composition: every component, exact
    versions, and one target harness. Replacing any component makes a new
    version of the setup.

=== "Component"
    In a component, what matters is the kind, the scope, and how it will affect
    the target: as text, as tool access, as a hook event, as a command, or as a
    setting.

??? question "Why the catalog is shown to people and to agents"
    A person judges meaning, trust and risk. An agent reads the same facts in
    machine form and should not fill in missing context from memory.

## Cache

The CLI may show an object from the local cache when the network is
unavailable. Such an answer says when the platform last confirmed the data.
