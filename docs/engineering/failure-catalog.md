---
description: "Historical failure lessons extracted from retired experiments, with current regression owners."
last_verified: "2026-09-04"
---

# Failure catalog

Historical experiment trees are not current evidence. This catalog records the
lessons that still have a regression owner in this repository. A new failure
joins this list only when it has a durable test, a contract owner, and a
command that can reproduce the refusal.

| Lesson | What failed | Current owner |
|---|---|---|
| Empty `releases` is not a wildcard | An unsigned OpenNetwork provider looked installable because the Ed25519 pin list was empty | `docs/contracts/provider-release.md`, `apps/cli/src/ai_stp_cli/provider/release.py` |
| Location is not trust | A `release.json` beside managed bytes was treated as verified because of its path | `docs/contracts/provider-release.md`, `apps/cli/src/ai_stp_cli/provider/acquire.py` |
| Missing adaptation is not a compile | Auto-acquired providers compiled a component that named no adaptation | `docs/contracts/eligibility-constraints.md`, `adaptation_unavailable` |
| Provider v3 is one target | Treating several roots as one provider commit invented atomicity the protocol does not have | `ADR-0145`, SPEC-058 |
| Index delivery is not a trust level | A PyPI wheel without PEP 740 verification would have been the easy unverified path | `ADR-0141`, `REQ-850` |
| Branch protection is not a gate | Required reviews would block the agent that writes `main` | `ADR-0115` |
| Six published internals are not one product | `uv tool install ai-stp-cli` depended on five other index projects remaining at the same version | `ADR-0146` |
| `clean` is not `passed` | Evidence that asked "did nothing fail" treated an all-inconclusive matrix as green | `docs/engineering/implementation-roadmap.md`, evidence scripts |
| Isolation unavailability is not enforcement | Reporting `enforced` when the launcher was absent hid Windows as ready | `docs/contracts/provider-protocol.md` |
| Experiments are history | Treating `ai-stp-experiments` runs as current six-leg evidence | `this catalog` |
| Scaffold apply is not `--confirm` | A second confirmation flag beside the plan digest would have been a weaker confirmation than the digest itself | `docs/contracts/component-authoring-templates.md`, `SPEC-041` |

Owners named above are the places a regression must break. This file does not
copy their rules.
