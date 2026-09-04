# Traps

These distinctions are not encoded in command names, and getting them wrong can
look like success.

- Read harness availability from `surface`, `version_source`, and `diagnostic`,
  not from the `version` string.
- `state: available` with an empty `installations` means supported but not
  installed. Do not call it installed.
- An accepted local passport is provenance and owner consent, not publish-ready
  or platform-verified.
- `ready: true` on passport validation is local structural completeness of one
  revision, not permission for a cloud write.
- A provider release signature does not prove compatibility. Both release trust
  and conformance are required.
- Only the catalog command intended for offline closure supplies its bytes. An
  object key is not authority to fetch.
- `candidate_id` is not a Component id. The Component id appears only after
  `component adopt`.
- Call a GitHub origin exact only with `provenance.kind: github` and
  `state: exact`. A cache directory name is not evidence.
- `harness_id: null` is not assigned to a harness by the agent.
- In browser device flow, show the verification URL and user code; do not
  complete the grant for the user.
- Do not construct web routes. Use `link web` for canonical links and
  `cli_argv`.
- `source: cache` is the past: show `checked_at` and do not present it as
  current cloud state.
