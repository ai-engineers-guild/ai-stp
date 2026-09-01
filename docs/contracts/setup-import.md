---
description: "Machine boundary for discovering and registering an existing native setup."
last_verified: "2026-09-01"
---

# Native setup import

The requirements owner is `SPEC-008` (`REQ-813`–`REQ-815`, `REQ-841`). This
document defines the observable CLI boundary and does not define native harness formats.

Import is divided into four actions: `discover`, `inspect`, `plan`, and `register`.
The first three write nothing. `register` executes only the exact plan that the user
confirmed after reviewing its effects.

`inspection_digest` binds the root, harness, sanitization rule, and file inventory.
`plan_digest` additionally binds the proposed component decomposition, exclusions,
blocking reasons, and effects. Changing any file read by inspection makes the previous
plan inapplicable.

The proposal's `file_set_digest` describes the inventory of paths, sizes, and file
hashes. It is not `ArtifactRef.digest`: the latter appears only after exact sanitized
bytes have been built. The CLI does not present a description of a future artifact as
verification of its content.

`setup import register` accepts `plan-digest`, `backup-ref`, and explicit `confirm`.
Before writing, the CLI repeats inspection and rebuilds the plan. A matching digest
authorizes one transaction that creates the backup reference, sanitized content-addressed
component artifacts, their individual passports, and the setup's own passport with
exact references to the created revisions. An error at any stage leaves neither part
of the graph nor an orphaned backup reference.

Registration is idempotent per plan digest: replaying the same confirmed
`plan-digest` — a client that died after the commit and before reading the
answer retries exactly this way — returns the graph the first run created,
never a second setup beside it.

An unread file is not silently skipped. It is listed in both `excluded` and `blocked_by`;
registering the complete setup is impossible until the cause is resolved. Secret values,
runtime cache, session state, and backup bytes are not transferred into the registry.

Component decomposition is read from the harness catalog — the same owner
`component discover` consumes — never from a second table (`ADR-0138`). A file
matching a layout with a `declared_key` yields a contribution candidate whose
boundary is `path#key`, whose native identities are the declared entry names,
and whose registered artifact carries only the extracted key value, sanitized
in the host file's own format. A file no layout claims is registered as a
per-file `setting`, never dropped and never guessed into another kind.

A registered component's artifact is stored in the same format `component
adopt` would have stored for that shape, with every member relative to the
component boundary rather than to the harness root: a single file as
`ai-stp-component-file/1`, a directory as `ai-stp-component-tree/1` sealed by
the one tree encoder, and a contribution as the extracted key value. The
passport records `source_name`, `content_format` and `managed_paths` exactly as
adoption records them, so a bundle compiled from an imported setup is the
bundle an adopted one would produce. Drafts registered before this rule in the
`ai-stp-imported-component/1` envelope remain readable.

Sanitization is structural per format: JSON, JSONC, TOML (comment-preserving),
and YAML documents are rewritten with credential values removed and environment
maps reduced to variable names; each file's inventory row records which rewrite
actually happened, and an unparsed or unstructured file is reported as not
rewritten rather than implied clean.

Inspection follows no link. A symlink, a Windows reparse point, a hardlinked
file, and a special file are each reported as refused with their reason;
registration re-reads every packed file without following links, re-checks the
inode it classified, and demands the bytes still hash to what the confirmed
plan recorded.

The setup passport pins the versions the capture was made with and against:
`capture_tool_version` always names the exact CLI, and `harness_version`
carries the detected installation's version — empty is the honest record of a
tree imported on a machine where the harness itself did not answer, never an
omission. `backup_verification` states `recorded_unverified` until a provider
status read actually confirms the reference.

Registration is complete by default: a plan whose inventory left anything out —
oversized, refused — is refused until the operator passes `partial`, and a
partial registration records `capture_mode` and the exact `excluded_paths` in
the setup passport, so the incompleteness travels with the object.
