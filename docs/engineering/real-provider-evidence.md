---
description: "How to run the full lifecycle against released providers and what is checked in the process."
last_verified: "2026-08-29"
---

# Proof Against Released Providers

The requirement owner is `#408`. `just evidence-providers <tag>` checks
release metadata and projection consent, and itself states what it cannot verify:

```json
"not_verified": {
  "install_update_backup_remove_rollback": "the cross-repository tests in
   tests/unit/test_cli_install_commands.py; they need AI_STP_<HARNESS>_PROVIDER_V3
   and _MANIFEST pointed at a fetched artifact and its release.json"
}
```

This is the half that the run below covers.

## How to Run

```bash
for h in claude-code codex grok-build opencode pi; do
  uv run ai-stp provider fetch --harness "$h" --json >/dev/null
done

export GH_TOKEN="$(gh auth token)"
for pair in CLAUDE:claude-code CODEX:codex GROK_BUILD:grok-build \
            OPENCODE:opencode PI:pi; do
  v=${pair%%:*}; h=${pair##*:}; d=~/.local/share/ai-stp/providers/$h/<tag>
  export AI_STP_${v}_PROVIDER_V3="$(find "$d" -maxdepth 1 -type f -perm -u+x | head -1)"
  export AI_STP_${v}_PROVIDER_V3_MANIFEST="$d/release.json"
done
export AI_STP_PROVIDER_V3_READONLY="$AI_STP_CLAUDE_PROVIDER_V3"

uv run pytest tests/unit/test_cli_install_commands.py -k "real_ or backups_reaches"
```

`GH_TOKEN` is mandatory, and the reason is not cosmetic: the tests substitute `HOME`, and
`gh` holds the credentials there. Without the token, the certification check refuses —
previously it refused with the words "the artifact does not have an acceptable certification," that is,
it blamed the bytes because there was no login on the machine. Now unauthenticated
`gh` (exit code 4) differs from the actual verdict (code 1) and is reported as an unavailable dependency.

## What was checked against `0.0.33`

```text
basic setup, full bundle cycle     claude-code codex grok-build opencode pi
full v3 cycle with a single precise bundle   claude-code codex grok-build opencode pi
reading provider backups   claude-code
```

Eleven runs, all green. Each takes the released signed artifact, checks GitHub attestation against the locked policy, builds the bundle, plans, applies, reads state, and rolls back.

## The corpus carries the seventh part of the published material

This was discovered while analyzing the same run and is unrelated to attestation.

Setup systems publish **28 setups: four for each of the seven harnesses**, and the axis is the **product pose**, not the role:

```text
minimal        instructions only; the product keeps its defaults
baseline       working floor: instructions plus a conservative permission rule
full-auto      nothing is asked, nothing is sandboxed
nddev-builder  working floor plus author’s set of NDDev
```

Our case builder reads `SOURCE_PATH = "setups/nddev-builder"` — **one** of four positions — and signs it `target_role: ai-harness-engineer`. Hence seven setups in the directory instead of twenty-eight, and a name that is in no source: it is set by the local builder.

Positions are sourced to vendor pages, and each carries `sources`. The role has nothing to source to, so that side does not publish them — a setup whose identity depends on someone’s preference would be the first there.

There is no longer a role-based E2E. It asked for six roles that no one planned, and could only fail when a real provider was connected — exactly in the only run where it is exercised. If the other three poses are imported, the test must cover **poses**, and that is a different test.

## Adjacent slices that also need to be known by name

`just evidence-citations` fetches every link that has the harness directory string on it and labels them as dead. Nothing in the repository opens the link, so the stale one is found by a person and no one else; on 2026-08-28, there were four of them.
403, 405, and 429 are considered unproven, not dead — some hosts refuse the script on HEAD.

`just corpus-drift` asks the source whether the first-person corpus has fallen behind in content (`docs/engineering/first-party-corpus.md`).

Both are mentioned here because until 2026-08-29 they were not mentioned anywhere a reader would look — and a check that cannot be found is worth exactly as much as one that no one runs. Neither is included in `just check`, for the same reason: the repository gate must not depend on someone else's site or network.

## What this does not prove

A clean installation from the site is a separate case; it is not here. And three out of four items are not checked because they are not in the directory.
