---
description: "Runbook: operator-managed official GitHub and package upstream component snapshots."
last_verified: "2026-09-04"
---

# Official upstream components

AI STP Official publishes attributed snapshots of curated public GitHub and
package components. The checked-in manifest at
`packages/contracts/src/ai_stp_contracts/official/manifest.json` is the only
production inventory: PostgreSQL is its projection, not a second source of
truth. A daily enqueue creates at most one `official_upstream_sync` job per
enabled source. The worker resolves each source through the shared
`SourceIntent`/`SourceSnapshot` adapters and reuses the existing plan, bind,
validate, and publish jobs. There is no public management endpoint and no
automatic ownership transfer, catalog replacement, or identity merge.

## Current Official inventory

The normal `seed` startup step idempotently creates the fixed public account:
ID `account_01KZET6ZKJN7S72T5H4WDV62T0`, handle `ai-stp-official`, display name
`AI STP Official`. The manifest currently declares 52 unique component lines
with exact source IDs, stable component IDs, and displayed names:

| Source ID | Stable component ID | EN display name | RU display name |
|---|---|---|---|
| `ai-stp-skill` | `component_01M1Q0S5JQXTZK8JQXN5JZXHR0` | AI STP Skill | Навык AI STP |
| `addyosmani-agent-skills` | `component_01M1MEBR4CAPFVBKG0J1G8Z8KN` | Addy Osmani Agent Skills | Addy Osmani Agent Skills |
| `agent-browser` | `component_01M1MEBR369ZWN0ERB08GN78ZA` | Agent Browser | Agent Browser |
| `ai-repo-safety` | `component_01M1J0CDZ9SN9EVKTQ18M97Q43` | ai-repo-safety | ai-repo-safety |
| `andrej-karpathy-skills` | `component_01M1MEBR2HW59MMKPSN6AQ6SEC` | andrej-karpathy-skills | andrej-karpathy-skills |
| `anthropic-cybersecurity-skills` | `component_01M1MEBR2B1FGN43KNFQVWZS8S` | Anthropic-Cybersecurity-Skills | Anthropic-Cybersecurity-Skills |
| `anthropics-skills` | `component_01M1MEBR2REKDD3E1YZ3JDJTFC` | Anthropic Skills | Anthropic Skills |
| `atlassian-mcp` | `component_01M1MEBQZ93X5RMV0Y3F4RTA21` | Atlassian MCP | Atlassian MCP |
| `bmad-method` | `component_01M1MEBR3KQAGYG170KDZS3M6N` | BMAD Method | BMAD Method |
| `browser-mcp` | `component_01M1MEBQY13BJZC23NVZRK4657` | Browser MCP | Browser MCP |
| `caveman` | `component_01M1MEBQZZXVB8YMAP5B7P957K` | Caveman | Caveman |
| `chrome-devtools-mcp` | `component_01M1MEBQWZZESMDXTHB49MY3JK` | Chrome DevTools MCP | Chrome DevTools MCP |
| `codeburn` | `component_01M1MEBQYWN2W4VXFFJXW9ZXFT` | CodeBurn | CodeBurn |
| `context7-mcp` | `component_01M1GDHCFBV4ETHJPJJNFFR74C` | Context7 MCP | Context7 MCP |
| `context-mode-mcp` | `component_01M1GET1ZDWM5MJFK2F7AFG1E5` | CTX context-mode MCP | CTX context-mode MCP |
| `dart-mcp` | `component_01M1MEBQXCWKBZN4SB1DDBTPV8` | Dart MCP | Dart MCP |
| `deepwiki-mcp` | `component_01M1MEBQWAS615EWT4ZVQ56SYV` | DeepWiki MCP | DeepWiki MCP |
| `ecc` | `component_01M1MEBR4JAZ3H6J1K6PCADD5Y` | Everything Claude Code | Everything Claude Code |
| `figma-mcp` | `component_01M1MEBQWR3X1BF49E3TZMX8XK` | Figma MCP | Figma MCP |
| `find-skills` | `component_01M1MEBR0SMG7RCASDPJDXH9SC` | find-skills | find-skills |
| `firecrawl-mcp` | `component_01M1MEBQY8KD235KDPY565NMXT` | Firecrawl MCP | Firecrawl MCP |
| `github-mcp` | `component_01M1MEBQV6VWN9GP38NEA57N1W` | GitHub MCP | GitHub MCP |
| `gitlab-mcp` | `component_01M1MEBQVG9X08SMPVX3XHNGQW` | GitLab MCP | GitLab MCP |
| `grep-mcp` | `component_01M1MEBQWHKXXQQG2YQYXKNV79` | Grep MCP | Grep MCP |
| `grilling` | `component_01M1MEBR0CZHGZTFGYTRRNGRNM` | grilling | grilling |
| `grill-me` | `component_01M1MEBR0J903BQ6MJ7YAF7B10` | Grill Me | Grill Me |
| `gsd` | `component_01M1MEBR1DB7QC0TNBKZDDWGJJ` | GSD | GSD |
| `gstack` | `component_01M1MEBR3SPNQG6HSZ6E3J0C5Z` | gstack | gstack |
| `impeccable` | `component_01M1MEBR05FD92YMM3YY4NP0Q6` | Impeccable | Impeccable |
| `keenable-mcp` | `component_01M1MEBQZHMWC0Y0KF7MGKV92H` | Keenable | Keenable |
| `last30days` | `component_01M1MEBR4R8PC9X78CCSWN3982` | last30days | last30days |
| `next-move-theory` | `component_01M1MEBR24Y5PVWX1CEQ9FBK3B` | Next Move Theory | Next Move Theory |
| `notion-mcp` | `component_01M1MEBR55Z264WW3Q7SZF6139` | Notion MCP | Notion MCP |
| `official-serena` | `component_01M1EYCA2G9FJ30F58WRPDQAM0` | Serena MCP | Serena MCP |
| `openai-docs-mcp` | `component_01M1MEBQXM2ZSDXHFRPW72FJPW` | OpenAI Docs | Документы OpenAI |
| `openmontage` | `component_01M1MEBR1XH4AH9A2T935SN3D3` | OpenMontage | OpenMontage |
| `openspec` | `component_01M1MEBR0ZNFHE1QR9J2Y02DA1` | OpenSpec | OpenSpec |
| `playwright-mcp` | `component_01M1MEBQXT9RWK9G81V6ECG1Y1` | Playwright MCP | Playwright MCP |
| `ponytail` | `component_01M1MEBQZR9AT0X0PHCCG78JB6` | Ponytail | Ponytail |
| `ralph` | `component_01M1MEBR1NKJFRG35WES54ABN2` | Ralph | Ralph |
| `semble` | `component_01M1MEBQYF2PS6BX57KDZ6ZRF9` | Semble | Semble |
| `sentry-mcp` | `component_01M1MEBR5SP631EYAJ2AHQ900S` | Sentry MCP | Sentry MCP |
| `shadcn-mcp` | `component_01M1MEBQX6YC099SJAPSS63FXG` | shadcn MCP | shadcn MCP |
| `slack-mcp` | `component_01M1MEBR5KZZ3A2N2P21AVG9RT` | Slack | Slack |
| `spec-kit` | `component_01M1MEBR3CBMZ4AJ8R657J1EBY` | Spec Kit | Spec Kit |
| `stripe-mcp` | `component_01M1MEBR651E23RYS6H4BM8KVS` | Stripe MCP | Stripe MCP |
| `supabase-mcp` | `component_01M1MEBR5ZFGQ53SSZGBMH7TDH` | Supabase MCP | Supabase MCP |
| `superpowers` | `component_01M1MEBR176Q46R75KMVEB8AP2` | Superpowers | Superpowers |
| `taste-skill` | `component_01M1MEBR45GNQ505MBNMY2CTG9` | Taste | Taste |
| `ui-ux-pro-max` | `component_01M1MEBR3Z39AVZMRBBTNW728J` | UI UX Pro Max | UI UX Pro Max |
| `understand-anything` | `component_01M1MEBR4Y2ZMXEHDEEAW7ECS0` | Understand Anything | Understand Anything |
| `vercel-agent-skills` | `component_01M1MEBR2YDBNTEZRE3NWT63SV` | Vercel Agent Skills | Vercel Agent Skills |

The manifest also fixes each repository, ref, component subpath, component
kind, attribution, exact stable ID, canonical name, and update policy. Add or
change a source by editing and reviewing that JSON file, then deploy and run
manifest reconciliation. Do not hand-edit or production-upsert a source row;
undeclared rows fail reconciliation and transferred/removed rows stay fenced.

### Public source links

The table below is the complete current inventory. Links point to the
official upstream repository or to the exact package release used by the
manifest; ctxt-mcp, the non-pullable Linear placeholder, and the retired
Vercel MCP placeholder are intentionally absent.

| Name | Type | Full official source link |
|---|---|---|
| Addy Osmani Agent Skills | skill | [https://github.com/addyosmani/agent-skills/tree/main/skills](https://github.com/addyosmani/agent-skills/tree/main/skills) |
| Agent Browser | skill | [https://github.com/vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) |
| AI STP Skill | skill | [https://github.com/ai-engineers-guild/ai-stp/tree/main/apps/cli/src/ai_stp_cli/skills/canonical](https://github.com/ai-engineers-guild/ai-stp/tree/main/apps/cli/src/ai_stp_cli/skills/canonical) |
| ai-repo-safety | skill | [https://github.com/letya999/ai-repo-safety-skill](https://github.com/letya999/ai-repo-safety-skill) |
| andrej-karpathy-skills | skill | [https://github.com/multica-ai/andrej-karpathy-skills/tree/main/skills/karpathy-guidelines](https://github.com/multica-ai/andrej-karpathy-skills/tree/main/skills/karpathy-guidelines) |
| Anthropic Skills | skill | [https://github.com/anthropics/skills/tree/main/skills](https://github.com/anthropics/skills/tree/main/skills) |
| Anthropic-Cybersecurity-Skills | skill | [https://github.com/mukul975/Anthropic-Cybersecurity-Skills/tree/main/skills](https://github.com/mukul975/Anthropic-Cybersecurity-Skills/tree/main/skills) |
| Atlassian MCP | mcp | [https://github.com/atlassian/atlassian-mcp-server/blob/main/server.json](https://github.com/atlassian/atlassian-mcp-server/blob/main/server.json) |
| BMAD Method | plugin | [https://github.com/bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) |
| Browser MCP | mcp | [https://github.com/BrowserMCP/mcp](https://github.com/BrowserMCP/mcp) |
| Caveman | skill | [https://github.com/JuliusBrussee/caveman/tree/main/skills/caveman](https://github.com/JuliusBrussee/caveman/tree/main/skills/caveman) |
| Chrome DevTools MCP | mcp | [https://github.com/ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) |
| CodeBurn | mcp | [https://github.com/getagentseal/codeburn](https://github.com/getagentseal/codeburn) |
| Context7 MCP | mcp | [https://www.npmjs.com/package/@upstash/context7-mcp/4.0.4](https://www.npmjs.com/package/@upstash/context7-mcp/4.0.4) |
| CTX context-mode MCP | mcp | [https://www.npmjs.com/package/context-mode/1.0.169](https://www.npmjs.com/package/context-mode/1.0.169) |
| Dart MCP | mcp | [https://github.com/dart-lang/ai/tree/main/pkgs/dart_mcp_server](https://github.com/dart-lang/ai/tree/main/pkgs/dart_mcp_server) |
| DeepWiki MCP | mcp | [https://github.com/CognitionAI/deepwiki](https://github.com/CognitionAI/deepwiki) |
| Everything Claude Code | plugin | [https://github.com/affaan-m/ECC](https://github.com/affaan-m/ECC) |
| Figma MCP | mcp | [https://github.com/figma/mcp-server-guide/blob/main/server.json](https://github.com/figma/mcp-server-guide/blob/main/server.json) |
| find-skills | skill | [https://github.com/vercel-labs/skills/tree/main/skills/find-skills](https://github.com/vercel-labs/skills/tree/main/skills/find-skills) |
| Firecrawl MCP | mcp | [https://github.com/firecrawl/firecrawl-mcp-server](https://github.com/firecrawl/firecrawl-mcp-server) |
| GitHub MCP | mcp | [https://github.com/github/github-mcp-server](https://github.com/github/github-mcp-server) |
| GitLab MCP | mcp | [https://github.com/zereight/gitlab-mcp](https://github.com/zereight/gitlab-mcp) |
| Grep MCP | mcp | [https://github.com/galprz/grep-mcp](https://github.com/galprz/grep-mcp) |
| Grill Me | skill | [https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me) |
| grilling | skill | [https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling) |
| GSD | plugin | [https://github.com/open-gsd/gsd-core](https://github.com/open-gsd/gsd-core) |
| gstack | plugin | [https://github.com/garrytan/gstack](https://github.com/garrytan/gstack) |
| Impeccable | skill | [https://github.com/pbakaus/impeccable](https://github.com/pbakaus/impeccable) |
| Keenable | mcp | [https://github.com/keenableai/keenable-mcp/blob/main/server.json](https://github.com/keenableai/keenable-mcp/blob/main/server.json) |
| last30days | skill | [https://github.com/mvanhorn/last30days-skill/tree/main/skills/last30days](https://github.com/mvanhorn/last30days-skill/tree/main/skills/last30days) |
| Next Move Theory | plugin | [https://github.com/zamesin/Next-Move-Theory-Canon-and-Skills](https://github.com/zamesin/Next-Move-Theory-Canon-and-Skills) |
| Notion MCP | mcp | [https://github.com/makenotion/notion-mcp-server](https://github.com/makenotion/notion-mcp-server) |
| OpenAI Docs | skill | [https://github.com/openai/skills/tree/main/skills/.system/openai-docs](https://github.com/openai/skills/tree/main/skills/.system/openai-docs) |
| OpenMontage | plugin | [https://github.com/calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) |
| OpenSpec | skill | [https://github.com/Fission-AI/OpenSpec/tree/main/skills](https://github.com/Fission-AI/OpenSpec/tree/main/skills) |
| Playwright MCP | mcp | [https://github.com/microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) |
| Ponytail | plugin | [https://github.com/DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) |
| Ralph | plugin | [https://github.com/snarktank/ralph](https://github.com/snarktank/ralph) |
| Semble | mcp | [https://github.com/MinishLab/semble](https://github.com/MinishLab/semble) |
| Sentry MCP | mcp | [https://github.com/getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp) |
| Serena MCP | mcp | [https://pypi.org/project/serena-agent/1.7.0](https://pypi.org/project/serena-agent/1.7.0) |
| shadcn MCP | mcp | [https://github.com/shadcn-ui/ui](https://github.com/shadcn-ui/ui) |
| Slack | plugin | [https://github.com/slackapi/slack-skills-plugin](https://github.com/slackapi/slack-skills-plugin) |
| Spec Kit | plugin | [https://github.com/github/spec-kit](https://github.com/github/spec-kit) |
| Stripe MCP | mcp | [https://github.com/stripe/agent-toolkit](https://github.com/stripe/agent-toolkit) |
| Supabase MCP | mcp | [https://github.com/supabase-community/supabase-mcp](https://github.com/supabase-community/supabase-mcp) |
| Superpowers | plugin | [https://github.com/obra/superpowers](https://github.com/obra/superpowers) |
| Taste | skill | [https://github.com/Leonxlnx/taste-skill/tree/main/skills](https://github.com/Leonxlnx/taste-skill/tree/main/skills) |
| UI UX Pro Max | plugin | [https://github.com/nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) |
| Understand Anything | plugin | [https://github.com/Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) |
| Vercel Agent Skills | skill | [https://github.com/vercel-labs/agent-skills/tree/main/skills](https://github.com/vercel-labs/agent-skills/tree/main/skills) |

Validate or project the inventory from a host that can reach PostgreSQL:

```sh
python -m ai_stp_platform.official_upstream validate
python -m ai_stp_platform.official_upstream reconcile
python -m ai_stp_platform.official_upstream status
```

## Daily enqueue

Every running worker enqueues once when it starts and again after the UTC date
changes. The daily idempotency key makes multiple workers and restarts safe.
Repeating the scheduler command on the same UTC day returns the existing job
and does not run the fetch again.

A developer with PostgreSQL access can enqueue a new attempt without an HTTP
endpoint. `--force` writes a distinct audited queue row; the running worker
picks it up. Disabled sources are skipped; an explicit `--id` of a missing or
disabled row is rejected. Payload remains only `source_id`.

```sh
python -m ai_stp_platform.official_upstream.enqueue
python -m ai_stp_platform.official_upstream.enqueue --force
python -m ai_stp_platform.official_upstream.enqueue --force --id ponytail
```

One source's failure, disable, or idempotency key does not affect another
enabled source. Disable a source to stop later enqueue for that row without
deleting published catalog versions, audit rows, or sync history. Ownership
transfer is a database-bound operation: it changes every historical catalog
row's current owner, appends an ownership revision, marks the source
`transferred` and `update_policy=disabled`, cancels pending outbox/jobs, and
fences running attempts. Reconciliation preserves that tombstone and cannot
reactivate it.

```sh
python -m ai_stp_platform.official_upstream disable --id ponytail
```

A matching embedded snapshot may produce a dismissible catalog-replacement
suggestion when canonical coordinate and artifact digest both match. The
suggestion never replaces, promotes, or merges identities.

## Verify

1. Each intended source row is `enabled` and owned by the Official account.
2. The worker processed `official_upstream_sync` for today's UTC date per
   enabled source.
3. Unchanged component bytes leave the last published version in place.
4. A new digest creates a canonical projection artifact and explicit adaptation,
   then the next unused minor version on that source's own stable line, followed
   by `validate` and `publish` jobs from the shared publication pipeline.
5. The published description starts with upstream project, repository or
   package coordinate, license, and maintainer attribution and ends with the
   ownership-claim notice.

`AI_STP_WORKER_GITHUB_TOKEN` is sent only to `api.github.com`. Without it,
GitHub allows 60 requests per hour per IP. Each git source uses two API
calls before the archive download, so a catalog of this size exhausts that
budget in one scheduler pass and jobs fail as `GitHub rate limit exceeded`.
A fine-grained token with public repository metadata read is enough; write
access and private repositories are not required. Redirects are followed
only to `api.github.com`, `github.com`, and `codeload.github.com`. The token
is never written to job payloads, source rows, logs, or descriptions. In
local compose it comes from gitignored `.env.dev` (`env_file`); do not set
an empty override in `environment`, which would wipe that value.

For delivery gaps or a worker crash, inspect the attempt ledger and outbox,
then run reconciliation. The status output includes attempt state/result,
retry count, queue and outbox IDs/states, error class/code, manifest digest,
provenance, plan ID, and timestamps. A failed attempt is retried only through
the bounded queue policy or an explicit `retry --id`; exhausted work remains
in the queue DLQ and the domain ledger as `dead_lettered`.

```sh
python -m ai_stp_platform.official_upstream reconcile-delivery
python -m ai_stp_platform.official_upstream retry --id ponytail
```

## Rollback

Disable the affected source so scheduling stops for that row. Immutable
published versions remain readable. A previous deployment can still read source
and sync rows.
