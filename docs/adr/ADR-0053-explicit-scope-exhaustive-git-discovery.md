---
description: "Decision to fully traverse an explicitly named Git discovery scope and honestly report incompleteness."
last_verified: "2026-08-09"
---

# ADR-0053: Complete Git Discovery Within an Explicit Scope

Status: accepted.

## Context

`SPEC-004` prohibits scanning the home directory or disk without an explicit scope, but the previous implementation additionally truncated the search at a depth of two. As a result, a valid repository below a workspace group or portfolio was missed. An access error and an entry limit were also converted into an empty result indistinguishable from a complete traversal with no findings.

A Git worktree stores `.git` as a regular file, and a nested repository may be located inside another project. A manifest-only directory and a Git repository remain distinct grounds for candidacy: a package inside a monorepo does not become a project, whereas a separate `.git` must be visible to the user.

## Decision

The CLI recursively traverses only the root explicitly passed to `project discover`. Traversing the entire home directory remains prohibited. The traversal does not follow symlinks, does not enter the closed list of vendor, VCS, cache, and build directories, and limits the number of entries in a single directory.

Within the permitted scope, every `.git` that is a directory or a worktree file creates exactly one candidate. The first repository within a workspace has kind `project`; a repository inside an already discovered project has `nested_repository` and is not registered automatically. The result is sorted by resolved local path and preserves markers and the reason for origin.

Every skip receives a closed diagnostic code: `excluded`, `symlink`, `entry_limit`, or `unreadable`. `entry_limit` and `unreadable` set `complete=false`; the CLI does not describe such a response as complete. System error text is not exposed: the diagnostic contains only the error class and a redacted path.

## Consequences

- the depth of an explicitly selected portfolio does not hide repositories;
- a complete traversal of a large scope may be more expensive, so the user selects the scope, while exclusions and the per-directory limit remain mechanical;
- the agent must show incompleteness and its reasons rather than selecting from a partial list as though it were exhaustive;
- discovery remains read-only and does not create a Project, passport, or registry;
- global native components belong to a separate harness layouts table and are not mixed with Git project traversal.

## Reconsideration Conditions

The decision will be reconsidered if a supported Git API provides a content-neutral worktree index without traversal, or if an explicit multi-root command is introduced. Each root must still preserve separate completeness and diagnostics.
