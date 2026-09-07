# Compose

User intents: select a setup, check eligibility, confirm a proposal.

Resolve from machine help: `ai-stp select eligibility`,
`ai-stp select eligibility-matrix`, `ai-stp select impact`,
`ai-stp select propose`, `ai-stp select confirm`, `ai-stp select cancel`,
`ai-stp select graph`, `ai-stp select reports`, `ai-stp setup compose plan`,
`ai-stp setup compose apply`, `ai-stp setup recast plan`,
`ai-stp setup recast apply`, `ai-stp component materialize plan`,
`ai-stp component materialize apply`, `ai-stp component portability plan`,
`ai-stp component portability apply`,
`ai-stp eval plan`, `ai-stp eval run`,
`ai-stp eval component plan`, `ai-stp eval component run`.

Read eligibility and reports before proposing. Confirm only the proposal just
returned, not an older row from a listing. `experimental` or unverified-author
members may enter under task authority and stay labeled; they do not become
`authoritative`. Verify with `ai-stp select graph` after confirm.

To recast a complete setup onto another harness, resolve `setup recast plan`
and `setup recast apply` from machine help. Apply only a complete plan. A
blocked member is not a setup. MCP files and host-file contributions derive;
settings, non-MCP contributions, and MCP plugin packages stay blocked.

To materialize one missing target adaptation of a pinned component, resolve
`component materialize plan` and `component materialize apply`. Repeat
`--to-harness` or pass `--all-missing` when the source is already correct for
every remaining closed harness. A blocked member fails the whole `--all-missing`
set. A claimed-portable install without a published adaptation is
`component portability plan` / `apply`, which forks a private overlay and never
mutates the public version. Compose the overlay into a private setup through
`select propose`; a public setup composition and publication refuse it.
