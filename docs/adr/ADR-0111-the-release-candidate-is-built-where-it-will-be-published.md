---
description: "Decision to build and attest the release candidate in the public repository because the package identity will live there as well."
last_verified: "2026-08-29"
---

# ADR-0111: The release candidate is built where it will be published

Status: accepted. Continues `ADR-0109` and `ADR-0110`, clarifying the placement
chosen by a decision that belongs to private infrastructure and is not
published here.

## Context

`release-candidate.yml` built an unpublished Python candidate and attested it
through GitHub/Sigstore build provenance. It lived in the private copy and was
inoperative there for two reasons, neither of which a run reported.

The attestation job was conditional:
`github.event.repository.visibility == 'public'`. The condition was deliberate—
artifact attestation is unavailable to a private repository on the current
plan—but it is always false in a private repository. A skipped job is not an
attested one, and the comment in the file said exactly that while awaiting the
repository becoming public.

Second, both jobs targeted a fleet class. An unregistered or unserviced class
does not fail but waits forever, so the workflow could remain unexecutable
while appearing valid. It has no runs.

A third reason appeared after `ADR-0109`: Trusted Publishing authenticates with
an OIDC token that names the repository. Only the repository that built the
package can upload it, and `ai-stp` will be public.

## Decision

`release-candidate.yml` belongs to the public tree and runs on standard GitHub
runners. The visibility condition is gone: attestation is available where it
now lives, and skipping is no longer a possible outcome.

The private copy does not build a candidate. A test requires that none of its
workflows request `attestations: write`.

The separation of authority from `ADR-0048` remains unchanged and for the same
reason: the build receives neither OIDC nor attestation permission, while the
attestation job downloads the bytes and performs no checkout. Ephemeral runners
provide this by construction—the machine that built the candidate no longer
exists when the second job starts. A shared runner image is not a shared
machine.

The workflow still performs no upload to PyPI. Publication requires a separately
protected environment and an explicit human decision, so the test fails if
`gh-action-pypi-publish`, `password:`, or `api-token` appears.

## Consequences

`#185` gets a place where it can happen: build, attestation, and—after a
separate decision—publication are performed by the single repository named by
the OIDC token.

The workflow contract moves to
`tests/contract/test_release_candidate_workflow.py` and is published because
the tree that builds must prove it. Checks of the candidate bytes themselves
remain in place.

The fleet class leaves the question: an ephemeral runner was required, not a
specific fleet, and a GitHub-hosted runner has this property by construction.

## Reconsideration conditions

Reconsider if the package identity moves to another repository or if a separate
environment appears that needs its own candidate.
