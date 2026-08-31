---
description: "Canonical domain glossary."
last_verified: "2026-08-24"
---

# Terms

| Term | Meaning |
|---|---|
| Harness | A coding agent CLI environment: Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor, or Antigravity. |
| Setup | The complete configuration of a specific harness; it belongs to one harness from the moment it is created. |
| Component | An individual part of a setup. |
| Component variant | A native implementation of a component for a specific harness. |
| Setup lineage | A provenance link between setups for different harnesses, without a shared version or shared access. |
| Native packaging | An object's delivery form: marketplace, plugin, native files, or package. |
| Passport | A versioned, machine-readable description of an object. |
| Device passport | A private, revisioned passport of one device's environment; it is not merged across devices. |
| Finding | An observed fact with `observed` provenance and `none` verification that has not yet been entered into a passport. It is not a separate entity. |
| Tag vocabulary | A closed, versioned list of tags allowed for publication. |
| `local_drift` | The target was changed outside the provider lifecycle and no longer matches the installed version's passport. |
| `catalog_drift` | A newer version is available for a pinned object. |
| Selected version | A version pinned by confirmation for a project-and-harness pair; it becomes installed after the provider reports `verified`. |
| `pending_install` | The normal window between confirmation of the selected version and a `verified` installation; it is not drift. |
| Draft | A mutable private working version. |
| Version | An immutable `X.Y` object with an exact digest. |
| Major line | All versions with the same `X`, for example `1.0–1.n`. |
| Local registry | One device's user-owned state. |
| Cloud registry | The platform's server-side metadata and artifacts. |
| Box | A colloquial name for a registry, local or cloud. It is not a separate entity and does not mean a setup. |
| Provider | A public setup manager for a specific harness. |
| Setup builder | The deterministic layer that validates composition and builds a bundle. |
| Selection | The path from search to composition: constraints, trust lane, ordering, and agent choice. The product does not choose on the user's behalf. |
| Composition proposal | A short-lived composition candidate in a recommendation session; it becomes a version only after explicit user confirmation. |
| HarnessBundle | A bounded package of files and `bundle.json` for a provider. |
| Attestation | A signed device report of local verification for an exact digest. |
| Verified author | An author whose identity or namespace ownership the platform has verified. |
| Verified component | A specific object version that has passed mandatory platform checks. |
| Trust lane | The rule governing a candidate's inclusion in results: authoritative, experimental, or `local_owner_or_pinned`. |
| Unverified consent | A request flag for a command or session, or a durable record for a publisher or an object's major line; the result always remains experimental. |
| Assurance | A set of independent integrity, validation, and compatibility evidence. |
| Target | An isolated directory for a specific harness installation. |
| Snapshot | An immutable record of state or an operation. |
| Grant | An explicit right for an account ID to an object and its major line: read, install, and fork without editing the original. |
| Fork | A new private object of the same kind for the recipient, created from an accessible object; an unchanged clone is not republished. |
| Invitation | An access offer sent to a verified email address that becomes a right only after sign-in. |
| Report | A private moderation case about an exact object version; it is neither a public issue nor an automatic block. |
