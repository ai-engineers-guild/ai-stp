---
title: "Catalog"
description: "How to read the public ai_stp catalog and what its results mean."
---

# Catalog

The public catalog helps you find setups and components by harness, tags,
compatibility, update date and trust line. Both mode lists setups first and
components after; each group keeps the sort you chose.

The website shows cards. The CLI searches, shows, versions, and fetches the
same public objects. Neither surface installs anything: installation is a
separate, digest-bound provider plan.

Web cards: [Web catalog](../web/catalog.md). What a scan result means:
[Security checks](../security-checks.md).

## Anonymous reading

The public catalog can be read without an account. That matters for a first
look, for local selection, and for an agent working before sign-in.

```bash
ai-stp registry search --kind setup --query frontend --json
ai-stp registry search --kind component --query playwright --json
ai-stp registry show --kind setup --id <stable_id> --json
ai-stp registry version --kind setup --id <stable_id> --version 1.0 --json
```

`--kind` is required: `setup` or `component`. There is no single mixed search
in the CLI; Both-mode is a web listing that concatenates the two halves.

Experimental objects sit in their own section and need an explicit flag:

```bash
ai-stp registry search --kind component --query scanner --include-experimental --json
```

`--include-experimental` lasts for that command only. It is not stored, and
it is not consent to install. Consent is [trust and safety](../trust-and-safety/index.md)
and `ai-stp consent allow`.

## Fetch and offline cache

Search and show may answer from cache when the network is down. The envelope
says when the platform last confirmed the bytes. Treat that as a dated
snapshot, not a live catalog.

To pin exact published bytes locally:

```bash
ai-stp registry fetch --kind component --id <stable_id> --version 1.0 --json
ai-stp registry acquire --id <setup_id> --version 1.0 --json
ai-stp registry acquire --id <setup_id> --version 1.0 --offline --json
```

`fetch` writes immutable content-addressed bytes into the local cache.
`acquire` takes one exact published setup graph for local offline
compilation. `--offline` uses only verified cached passports and artifacts.

## Web versus CLI

| Job | Web | CLI |
| --- | --- | --- |
| Browse cards, Both-mode, sort | yes | no mixed Both search; two `--kind` searches |
| Read a public object without an account | yes | `registry search` / `show` / `version` |
| Fetch exact bytes into the local cache | no | `registry fetch`, `registry acquire` |
| Select, compose, install | no | select, setup, install groups |
| Publish | account UI plus CLI confirm | `publication` and `setup publish` |
| Report a problem | report UI | `report preview` then `report confirm` |

The website does not assemble a setup and does not write native harness
state. If a card looks right, the next command is still on the CLI.

## Both-mode

On the web, Both mode lists setups first, then components. Each group keeps
the sort you chose: you do not get a single blended ranking that hides which
half an object belongs to.

In the CLI, run two searches if you need both halves, then compare harness,
`X.Y`, trust line, and the two verification axes yourself.

## What to look at in a result

Before choosing an object, check:

- the harness and the supported version;
- the exact version of the object (`X.Y`, not a range);
- provenance and the source commit;
- `author_verified` and `component_verified`;
- the trust line;
- compatibility constraints;
- the result of the last check, including the catalog percent.

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
| Checks | which scans passed, failed, or did not run | a high percent that hides skipped required checks |

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
Do not treat a cache hit as a newly verified publication.

Related command pages: [Registry](../cli/registry.md),
[Select](../cli/select.md).

## Related pages

- [Web catalog](../web/catalog.md) — the same objects as cards.
- [Quickstart for people](../quickstart/human.md) — first anonymous search.
- [Quickstart for agents](../quickstart/agent.md) — a result is a candidate.
- [Components](../components/index.md) — the closed kinds on a card.
- [Setups](../setups/index.md) — composition is not this listing.
- [Trust and safety](../trust-and-safety/index.md) — trust line and axes.
- [Security checks](../security-checks.md) — what the percent covers.
