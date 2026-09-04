---
description: "Build, verify, publish, yank, and recover a Python release."
last_verified: "2026-09-04"
---

# Python package release

## Candidate preparation

On a clean exact SHA, `apps/cli/pyproject.toml` carries the public version.
The candidate is one `ai-stp-cli` wheel and sdist; first-party modules ship
inside that wheel and metadata has no `Requires-Dist` for former internal
`ai-stp-*` projects (`ADR-0146`). Local checks without publication:

```bash
just check
just release-candidate
just release-candidate-install
```

`dist/release-candidate/` contains one wheel, one sdist, deterministic
`ai-stp-cli.cdx.json`, `release-manifest.json`, and `SHA256SUMS`. The builder creates
artifacts twice in temporary directories and fails on any mismatch. The archive
gate normalizes separators and Unicode identically for wheel and sdist, rejecting
absolute and parent paths, Windows drive paths, duplicates and case collisions, as
well as symbolic/hard links, devices, sockets, and pipes.
A dirty tree is disallowed by default; `--allow-dirty` is only for development
characterization and creates no release evidence.
The `--replace` flag replaces only a previously created candidate whose manifest and
`SHA256SUMS` fully cover unchanged regular files. An arbitrary, incomplete, or
modified directory is not release output and is not removed.

`release-candidate-install` runs outside the source tree, installs only the
`ai-stp-cli` wheel as a direct source, checks its URL through PEP 610 and SHA-256,
proves bundled first-party modules are present and not extra distributions, runs
`version`, `capabilities`, and `help --agent`, then removes the program.
`--find-links` without a direct binding is not evidence: with a matching version,
the resolver may take a package with the same name from the public index. The exact
versioned command for the site is in `release-manifest.json` as `install_command`;
before actual publication it remains release metadata, not a promise that the
package is available on PyPI.

In the GitHub workflow, `release-candidate` is manually run on the selected ref. An
exact version is supplied, and the ref must always be tag `v<version>`; there is no
remote mode without this check. Artifact attestation counts only after the
`attest-public-candidate` job succeeds, not merely when the workflow file exists.

## External publication prerequisites

Before adding or enabling a publish job, the repository owner separately confirms:

1. the repository is public;
2. both `release-candidate` jobs run on standard GitHub-hosted `ubuntu-latest`
   runners with different executors: the build receives no OIDC, and attestation
   performs no checkout (`ADR-0048`);
3. the `pypi-cli` environment is protected by required reviewers and rejects
   arbitrary branches; there are **two** reviewers, otherwise publication stops
   when one person is unavailable. After the unified `0.0.17` release, the
   obsolete `pypi` / `pypi-*` GitHub environments are removed; only `pypi-cli`
   remains;
4. the PyPI Trusted Publisher for `ai-stp-cli` pins the owner, repository, exact
   `publish-pypi.yml` workflow name, and environment `pypi-cli`;
5. exact-SHA `just check`, Linux x86_64 install evidence, SBOM, checksums, and
   provenance are green;
6. separate explicit permission for the actual publication has been obtained.

Branch and tag protections are no longer in this list: the repository does not
carry them under `ADR-0115`. What remains mandatory is the exact-SHA gate because it
checks the tree, not permission.

## Publication

The `publish-pypi.yml` workflow publishes. It is manually started
(`workflow_dispatch`) for `cli`. Inputs are the exact version without a leading
`v` and the `run_id` of the `release-candidate` run whose attested bytes are loaded.

There is no repository checkout: the job downloads that run's artifact, verifies
every `SHA256SUMS` line, selects exactly two distributions for `ai-stp-cli`,
and uploads them through `pypa/gh-action-pypi-publish`. It uses only
`id-token: write` and the official action pinned to a commit SHA; username,
password, and API tokens are forbidden.

Environment: `pypi-cli`. There is no internal publication order: one project is
uploaded.

### Run the script, not the steps by hand

```sh
uv run python release_scripts/publish_pypi.py --version 0.0.4 --run-id 32912847053
```

The script dispatches, approves, waits, and verifies **with PyPI** one package at a
time. It skips an already published package, so rerunning is safe.
`--dry-run` checks inputs and stops.

Three things it handles that were previously done incorrectly by hand:

- **Dispatches cannot run simultaneously.** `publish-pypi` has one
  `concurrency` group: each new run takes it, and the waiting run dies. On August
  25, three of five runs were lost this way.
- **`run_id`, not version, determines which bytes are uploaded.** One version may
  have several attested candidates—`0.0.4` had three because the tag moved three
  times—and PyPI is immutable. The script compares the candidate head with the tag
  before the first dispatch and refuses a mismatch.
- **PyPI, not GitHub, confirms publication.** A green run and a served file are
  different claims.

**Never approve a `publish-pypi` run whose inputs cannot be read.** The API does not
return `workflow_dispatch` inputs, so a waiting run's `run_id` is unknown. Cancel
that run and start again with named inputs.

### Who confirms

The `pypi*` environments list **`letya999` and `rldyourmnd`**;
`prevent_self_review` is `false`. Two-person control remains: either person can
confirm, rather than depending on one person whose absence delayed publication for
a day on August 25. Approval is performed through the API, so publication needs no
manual steps.

No upload token exists here, on the host, or in repository or organization secrets—
Trusted Publishing issues an OIDC identity for the run. There is no credential to
look for.

Live index on 2026-09-04: `ai-stp-cli==0.0.17` from candidate `33850604873`,
tag `v0.0.17`, commit `9e03ab27`, GitHub Release
`https://github.com/ai-engineers-guild/ai-stp/releases/tag/v0.0.17`. A clean
`uv tool install --python 3.14 --no-cache ai-stp-cli==0.0.17` installs one
first-party distribution. `provider fetch --harness pi` bound OpenNetwork
`0.0.61` at `trust_level=verified_publisher`. Wheel digest
`sha256:94e6f1a41b2f9b6bb9fba0c16bf6c7c2306bcaf6327b7eae35d7b751ccdbf9fb`
matches PyPI.

**Former internal projects are no longer part of the install.** They remain
on the index as `0.0.16` artifacts until their PyPI owners delete those
projects in the web UI with password confirmation: `ai-stp-sources` is
`rldyourmnd`; `ai-stp-foundation`, `ai-stp-passports`, `ai-stp-assurance`,
and `ai-stp-contracts` are `artemletya`. There is no upload token and no
deletion API. Do not delete them before `0.0.17` is on the simple index;
`ai-stp-cli==0.0.16` still requires them. Earlier: `0.0.6` from candidate
`33020095240`, `0.0.5` from `33008640398`.

Verified **with PyPI**, not from a green run:

- one project, `ai-stp-cli`, with a wheel and sdist; historical `0.0.16`
  internals remain on the index until their owners delete those projects;
- attestation of the published wheel succeeds and names its source—workflow
  `release-candidate.yml@refs/tags/v0.0.5`, commit `6514a36b…`. The negative
  control (random bytes) returns 404, so the check distinguishes them;
- `uv tool install --no-cache ai-stp-cli` without a pin in a clean `HOME` returns
  `0.0.5`;
- on the same installation: `harness install|update|remove`, `select propose
  --empty`, `scoped_projection_profiles` in the closed set, `provider trust`—schema
  2 with seven `build_attestations`—and anonymous `registry search --kind setup`—18.

### The index installers read lags behind the convenient one to query

Do not verify a release by installing immediately after publication. The JSON API
(`pypi.org/pypi/<name>/json`) updates before the **simple index**
(`pypi.org/simple/<name>/`), while installations use the latter, and CDN edges
converge unevenly across packages.

This was observed on `0.0.6`: the JSON API already returned the new version for all
five, while the simple index showed it only for `foundation` and `cli`. The window
was narrow—it converged within half a minute—but during it an unpinned installation
could take the new `cli` and fail to find the same-version `passports`, because
that `cli` pinned the other four exactly. `0.0.17` has no internal pins, so that
particular window cannot recur; the simple index can still lag the JSON API.

Therefore the verification order is: wait until `ai-stp-cli` appears in the simple
index, then install. `--no-cache` does not solve this; the issue is which index
answers, not the uv cache.

```sh
for p in cli; do
  curl -sS -H 'Accept: application/vnd.pypi.simple.v1+json' \
    "https://pypi.org/simple/ai-stp-$p/" | grep -c '0\.0\.X'
done
```

### Verify attestation, not a local rebuild

When `0.0.5` was checked, all ten local candidate digests **differed** from the
published ones. This looked like byte substitution and required an investigation.
There was one difference:

```text
CI:       Generator: uv 0.12.1
local:    Generator: uv 0.11.30
```

Every shipped module was byte-identical; `uv` stamps its version into
`dist-info/WHEEL`, and `RECORD` hashes it. The gate pinned `UV_VERSION` for itself,
but nobody told the developer's machine.

This is now pinned: `.uv-version` and failure on `just release-candidate`, following
the `bun` model. **With pinned `uv`, a clean worktree on the tag rebuilds the
`ai-stp-cli` wheel and sdist with digests identical to those served by PyPI**—the
build was always reproducible; uv's version was the only unpinned input.

The correct check for a received artifact is `gh attestation verify`, not a rebuild
and diff. A rebuild answers "did my toolchain match?"; attestation answers "where
did these bytes come from?"

## Failure and yanking

- PyPI files and versions are immutable; repeating with different bytes is forbidden.
- After a failed upload, do not retry the same version with different bytes. The
  fix receives a new patch version.
- A compromised or erroneous release is yanked with a public reason; bytes are not
  deleted and historical checksums are retained.
- Trusted Publisher/environment access is blocked during investigation; there is
  no permanent token to rotate.
- The last known-good version is explicitly pinned in installation documentation
  and the release manifest. Automatic downgrade of a user installation is forbidden.
