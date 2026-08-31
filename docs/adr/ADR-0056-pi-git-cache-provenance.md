---
description: "Exact provenance of Pi Git packages from the declared global cache without reading user settings or invoking Git."
last_verified: "2026-08-09"
---

# ADR-0056: Provenance of Pi Git packages from the cache

Status: accepted.

## Context

Pi documents global Git packages in
`~/.pi/agent/git/<host>/<path>` and pins the checkout to a ref or commit.
At the same time, `settings.json` is a shared settings file and may contain
sensitive values unrelated to discovery. Reading it in full for the sake of
a single packages array violates the read-only discovery boundary.

Invoking `git` is also unnecessary: it would expand the executable surface and
could inherit user configuration. The declared cache layout and the exact Git
`HEAD` are sufficient to establish provenance.

## Decision

The source adapter enumerates only three levels under `git/`:
host, owner, and repository. It does not follow symbolic links and fails closed
when the entry limit is exceeded or a read error occurs. Exact GitHub
provenance is created only for the `github.com` host, valid owner/repository
segments, and a checkout with a safe exact `HEAD`.

`HEAD` is read either as a detached 40-character SHA or as a safe reference
under `refs/heads/*`/`refs/tags/*`. The revision is obtained from a bounded
loose ref or `packed-refs`. The adapter does not read working files, Git config,
credentials, or `settings.json`, and does not invoke Git, package code, hooks,
or the network.

The finding receives `github/exact`, a canonical HTTPS repository, the
checked-out revision, package identity, and evidence `pi:git-cache-layout` plus
`git:checked-out-head`. This proves the source of the observed checkout, but
does not assert that the package is enabled by the current settings, clean
relative to the index, or verified by the platform.

A non-GitHub host does not receive a false GitHub claim. A corrupted or
floating checkout does not disappear from the regular declared Pi layouts, but
the cache package is not reported as exact and is accompanied by safe
diagnostics.

## Consequences

- a global Pi Git package has a stable source identity without access to shared
  user settings;
- loose and packed refs produce the same result;
- enabled/disabled state is intentionally not inferred;
- npm packages require a separate `package/observed` adapter without asserting
  a GitHub source;
- changes to the cache layout or the Git storage contract require the adapter
  to be reviewed.

## Review Conditions

The decision must be reviewed if Pi introduces a separate signed installation
ledger, if the cache layout changes in a documented manner, or if it becomes
necessary to prove that the entire checkout is clean relative to the Git index.
