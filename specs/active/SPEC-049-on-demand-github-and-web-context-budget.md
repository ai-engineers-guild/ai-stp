---
description: "SPEC-049: On-demand GitHub metadata, CLI-only blast radius, and an honest context budget in Web."
last_verified: "2026-08-16"
---

# SPEC-049: On-demand GitHub metadata and Web context budget

## Purpose

Simplify the exact-version card: GitHub stars and archive status are read once
when exact detail is opened, the archive badge appears only for an actually
archived repository, blast radius remains a local CLI operation, and Web shows
a reproducible estimate for the published setup without imitating local model
usage. The local dev build serves browser-facing `/v1` media without Caddy.

## Scope

Included:

- restoration of the dev-only `/v1/*` proxy and avatar/media smoke test on `localhost:3000`;
- one bounded on-demand GitHub metadata request for exact component/setup detail;
- a single minimal `stars` + `archived` response, without polling/history UI;
- removal of the server/Web blast-radius projection while preserving the CLI contract;
- a shared deterministic estimator for CLI and server projection;
- a public/owner exact setup context-budget endpoint and Web panel;
- a client-only cost calculator with an explicitly entered rate;
- owner Git identity/signing policy in `AGENTS.md`.

Excluded: actual model usage telemetry, an external tokenizer/pricing API,
automatic lifecycle changes, Web access to the local registry or installed
targets, production/Caddy deployment, and import of a local CLI report into Web.

This specification supersedes the server/Web delivery requirements of `SPEC-047`
`REQ-4705`…`REQ-4712` with respect to periodic GitHub archive evidence and
account blast radius. The local meanings of `SPEC-043` and `SPEC-044` remain
only where they are not explicitly superseded by this specification.

## Terms

- **GitHub metadata** — a best-effort pair of `stars` and `archived`, obtained
  for the repository from the immutable exact-version passport when detail is opened.
- **Context budget** — a deterministic estimate of the text context that the
  exact setup graph may load, not actual model usage.
- **Cost estimate** — client-side arithmetic over the context budget and an
  input-per-million rate explicitly entered by the user.

## Requirements

- `REQ-4901`: `docker-compose.dev.yml` runs `Dockerfile.dev`/`next dev` and
  proxies `/v1/*` to `AI_STP_API_BASE_URL` without Caddy. Avatar and component
  media are available through the Web origin; production routing is not
  duplicated in Next.

- `REQ-4902`: The detail page initiates exactly one GitHub metadata request. The
  API accepts an exact catalog coordinate, resolves the repository itself from
  the visible immutable passport, and calls only the fixed public
  `api.github.com` endpoint, with bounded timeout/size, no credentials, and no
  redirects.

- `REQ-4903`: The GitHub metadata response contains only nullable non-negative
  `stars` and nullable boolean `archived`. `403/404/429/5xx`, timeout, malformed,
  oversized, private/unsupported source produce both nullable fields without
  causing detail to fail.

- `REQ-4904`: GitHub metadata is not requested for catalog lists/cards. The
  detail header shows stars when a value is available and a compact `Archived`
  badge next to the GitHub link only when `archived=true`; active/unavailable/failure
  states do not create a badge, panel, freshness indicator, attribution, or proposal.

- `REQ-4905`: Periodic server archive polling, the archive latest/history
  projection, and the Web evidence panel are removed from the active path. Old
  queued derived jobs complete safely as superseded/no-op; derived cache storage
  is removed through a forward migration with rollback limited to an empty structure.

- `REQ-4906`: Web and the server API do not expose blast radius. The local
  `select blast-radius` command, `BlastRadiusReport`,
  `authority_boundary=local_registry`, and its tests remain unchanged; Web may
  only copy the exact CLI command.

- `REQ-4907`: One shared pure estimator is used by the CLI and server. It
  validates the exact graph/digests, counts `instruction` as always-loaded,
  `skill`, `agent`, and `command` as conditionally-loaded, distinguishes exact
  UTF-8 bytes from estimated Unicode codepoints/4, and does not treat
  unreadable/missing bytes as zero.

- `REQ-4908`: An exact setup context estimate is publicly available only for a
  public version, while a private version is available only to its owner. The
  response contains the coordinate, estimator, always/conditional/total,
  unavailable-component count, and a breakdown by component, but not artifact
  bytes, the account inventory, local selection, or installation.

- `REQ-4909`: The setup card shows the context estimate to everyone who can view
  the exact version. The panel resides in the right rail, not the left/main
  column, in the order Author → Context budget → Use via CLI → Version history;
  on a narrow screen, the same document/accessible rail order is preserved. The
  collapsed surface contains only the heading, one sentence, and the potential
  total; the always/conditional breakdown, component contributions, and cost
  estimate open in the first disclosure. The estimator profile is not shown by
  default. The unavailable state is explicit; the interface states directly
  that this is an estimate of potential context, not actual model usage.

- `REQ-4910`: The cost calculator runs only in the browser using the formula
  `total * input_per_million / 1_000_000`, does not persist input, and does not
  call a pricing API. Without a valid explicitly entered rate, the amount is
  absent; no stale/actual price is invented.

- `REQ-4911`: The personalized baseline/delta based on installed/selected state
  remains in the local CLI `select impact`. Web does not show a baseline guessed
  by the server. The copy command for the local report is hidden in a second
  “Check locally” disclosure inside the budget and is not mixed with the
  “Use via CLI” installation block in the rail.

- `REQ-4912`: Commit/tag/PR/MR identity follows `AGENTS.md`: name/email are
  obtained dynamically only from the current user's global Git config,
  effective author/committer must match them, and the agent does not change
  identity/signing config or substitute the author.

## States and errors

- GitHub: `ready`, `unavailable`; UI distinguishes only the presence of stars
  and `archived=true`; failure hides optional metadata.
- Budget: `ready`, `unavailable`, `invalid_graph`; a partial total is forbidden
  when the exact graph cannot be proven.
- Cost: `empty`, `invalid`, `available`; the amount is always labeled as an estimate.
- Media: the dev same-origin proxy returns the original API status/content type.

## Security and privacy

- The GitHub URL is not accepted from the browser; the source is derived from
  the exact passport.
- No GitHub credentials, raw response, ETag/history, or private repository
  distinctions are returned.
- The public estimate does not expose bytes, filenames beyond the accepted
  contract, or private coordinates. Owner verification is performed before
  reading a private graph.
- The client-side rate input is neither sent nor persisted.
- Web does not receive device identifiers, projects, installed targets, or the
  local registry.

## Compatibility and migration

1. Add the shared estimator and new additive metadata/budget endpoints.
2. Migrate the detail UI to them and remove archive/blast consumers.
3. Update generated contracts/clients.
4. Make old archive jobs no-op, then remove only the derived cache through a new
   migration. Fields used by old clients are removed from the wire in a
   coordinated manner before release.
5. The local container is rebuilt through the standard dev compose; this step
   does not change the production topology.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-4901` | The dev compose smoke test receives 200 and an image content type for avatar/media through `localhost:3000`; the browser image has `naturalWidth > 0`. |
| `REQ-4902` | The detail component test counts one metadata request; SSRF/redirect/credential negative tests pass. |
| `REQ-4903` | API fixtures cover 200 active/archived, timeout, 403/404/429/5xx, malformed/private/oversized. |
| `REQ-4904` | The list test proves zero GitHub calls; the header test shows the badge only when `archived=true`. |
| `REQ-4905` | The queue compatibility test accepts an old job; migration upgrade/downgrade affects only the derived cache. |
| `REQ-4906` | The generated API/Web inventory contains no account blast radius; CLI blast-radius tests remain green. |
| `REQ-4907` | Shared fixtures produce identical CLI/API output for files, ZIP, UTF-8, non-UTF-8, and digest failures. |
| `REQ-4908` | Public/owner/outsider matrix and exact graph negative tests pass without bytes/account leakage. |
| `REQ-4909` | RU/EN component tests verify the collapsed total, hidden jargon, empty/error states, and the “not usage” wording. E2e keeps the budget inside `component-detail-rail`, not `component-detail-main`, and preserves the Author → Context budget → Use via CLI → Version history order on desktop and mobile. |
| `REQ-4910` | Browser/unit tests verify the formula, rounding, empty/invalid input, and absence of network/storage writes. |
| `REQ-4911` | Web does not read installed/selected state; the copy command is visible only after the nested disclosure is opened. |
| `REQ-4912` | Policy test/agent review verifies global/effective identity parity and prohibits hardcoding/overrides; signing behavior is inherited unchanged. |
