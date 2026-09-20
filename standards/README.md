# Standards

One document per technology the system is built on. A standard names the
version contract, the rules that are checked mechanically, the features that
are accepted and the ones that are rejected — with the reason, because a rule
without its reason gets re-litigated every time it is met.

These are internal working rules for this working copy, like `AGENTS.md`:
they are withheld from the public export in
`release_scripts/public_manifest.toml`.

## Index

| Document | Technology | Covers |
| --- | --- | --- |
| [just.md](just.md) | `just` command runner | version contract, file structure, naming taxonomy, settings and attribute policy, the local-only/CI parity boundary |
| [docker.md](docker.md) | Docker + Compose + deploy chain | digest pinning, apt/apk policy, image/context rules, compose invariants, pull-model deployment, the `infra-*` just surface |
| [setup-systems.md](setup-systems.md) | Seven Rust setup-system providers + protocol v3 | kit/version contract, reader-first rollout order, pinned trust policy, per-tag evidence |

## Writing a standard

- One file per technology, named after the tool: `just.md`, `uv.md`,
  `pytest.md`.
- Required sections, in order: **Version contract**, **Rules**,
  **Accepted and rejected features**, **Verification**. A technology with no
  rejected features still gets the section — an empty section says the
  question was asked.
- Rules cite the mechanism that enforces them (a test, a lint, a gate
  recipe). A convention nothing checks is a wish, not a standard.
- Reasons name the incident or the measurement that produced the rule where
  one exists. Rules bought with an incident are the strongest ones this
  repository has; the incident is part of the standard.
- English only, same as code and commits.
