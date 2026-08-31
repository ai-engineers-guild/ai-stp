---
description: "Machine boundary for discovering and registering an existing native setup."
last_verified: "2026-08-12"
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

An unread file is not silently skipped. It is listed in both `excluded` and `blocked_by`;
registering the complete setup is impossible until the cause is resolved. Secret values,
runtime cache, session state, and backup bytes are not transferred into the registry.
