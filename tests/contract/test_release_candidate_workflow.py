"""What the release-candidate workflow must guarantee, where it runs.

Split out of the working copy's `test_release_candidate.py` when the workflow
moved here (`ADR-0111`). What stayed behind asserts the candidate bytes; what is
here asserts the workflow, and belongs with it — the repository that will hold
the package's identity is the one whose build has to be provable.
"""

from __future__ import annotations

import re

import pytest
from release_scripts import build_candidate

#: Only the tree that builds the candidate carries this. The working copy
#: stopped carrying it, and asserting a file it must not have would fail there
#: for the right reason and the wrong outcome; the property that matters for
#: that tree is the opposite one, asserted in `test_release_candidate.py`.
WORKFLOW = build_candidate.ROOT / ".github" / "workflows" / "release-candidate.yml"


def _workflow() -> str:
    if not WORKFLOW.is_file():
        pytest.skip("this tree does not build the release candidate (ADR-0111)")
    return WORKFLOW.read_text(encoding="utf-8")


def test_candidate_workflow_has_attestation_but_no_publish_authority() -> None:
    """Attestation authority, and deliberately nothing that can upload.

    Publication needs a separately protected environment and an explicit
    authorisation, so a credential reachable from here would be the whole
    protection undone by a convenience.
    """
    workflow = _workflow()

    assert "workflow_dispatch:" in workflow
    # A tag is what makes a candidate a candidate. Checked before checkout, so
    # a wrong ref never reaches repository code.
    assert 'expected_ref="refs/tags/v${EXPECTED_VERSION}"' in workflow
    assert "--require-tag" in workflow
    # The workflow calls only release scripts that exist. It invoked
    # `verify_protections.py` for a while after `ADR-0115` deleted it, and
    # nothing noticed until the first ever dispatch: this file asserts what the
    # workflow must contain, never that what it contains can run.
    #
    # Both invocation forms, because the workflow uses both: a path for
    # `build_candidate.py` and `-m` for `verify_candidate_install`.
    called = {f"{name}.py" for name in re.findall(r"python -m release_scripts\.(\w+)", workflow)}
    called |= set(re.findall(r"python3? release_scripts/(\S+\.py)", workflow))
    called |= set(re.findall(r"python release_scripts/(\S+\.py)", workflow))
    assert called, "no release script is invoked; this assertion would guard nothing"
    missing = sorted(
        name for name in called if not (build_candidate.ROOT / "release_scripts" / name).is_file()
    )
    assert not missing, f"the workflow runs {missing}, which are not in the tree"

    assert "python -m release_scripts.verify_candidate_install" in workflow
    assert '--expected-sha "${GITHUB_SHA}"' in workflow

    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    # The property, not the commit. This named one exact SHA, so every
    # legitimate bump of the action broke it — a dependabot pull request sat red
    # for exactly that reason, and the test was asserting a fixture's value as
    # if it were an invariant.
    #
    # What matters is that the step runs this action and that it is pinned by
    # commit rather than by a tag a publisher can move, which is the reason
    # `dependabot.yml` pins actions by commit at all. Which commit is a fact for
    # review, and a review is what a dependabot pull request is.
    pinned = re.search(r"uses:\s*actions/attest-build-provenance@([0-9a-f]{40})\b", workflow)
    assert pinned, "the attestation step is absent or not pinned by a 40-character commit"

    for forbidden in ("gh-action-pypi-publish", "password:", "api-token"):
        assert forbidden not in workflow.lower(), forbidden


def test_candidate_workflow_binds_the_selected_python_and_isolates_uv() -> None:
    workflow = _workflow()

    assert "UV_PYTHON=${python_path}" in workflow
    assert "UV_PROJECT_ENVIRONMENT=${RUNNER_TEMP}/ai-stp-release-python-3.14" in workflow
    assert '--expected-python "3.14"' in workflow


def test_candidate_build_cannot_persist_into_the_oidc_attestation_runner() -> None:
    """Separation is a property of the machine rather than of two machines.

    `ADR-0048` asked for two permanent roles that do not share a host, a user or
    a filesystem. Disposable per-job runners replace them: the machine that ran
    the build is gone before the attestation job starts, so there is nothing
    left to persist into. What still has to be asserted is the authority split,
    which is what the two roles were protecting.
    """
    workflow = _workflow()
    build, attest = workflow.split("\n  attest:\n", maxsplit=1)

    assert "id-token: write" not in build
    assert "attestations: write" not in build

    # The attesting job takes bytes and never repository code, so nothing it
    # signs can have been produced by something it checked out itself.
    assert "actions/checkout@" not in attest
    assert "id-token: write" in attest
    assert "attestations: write" in attest


def test_the_attestation_is_not_silently_skipped_where_it_cannot_run() -> None:
    """A skipped job is not called attested.

    The workflow used to guard the attesting job with a visibility condition,
    because artifact attestation is unavailable to a private repository. It
    lived only in a private one, so the guard was permanently false and the
    evidence permanently absent while the workflow reported success.
    """
    workflow = _workflow()

    assert "github.event.repository.visibility" not in workflow
    attest = workflow.split("\n  attest:\n", maxsplit=1)[1]
    assert "\n    if:" not in attest


def test_no_release_workflow_addresses_a_runner_this_tree_cannot_reach() -> None:
    """Hosted runners here, by name, so nothing queues forever unreported.

    An unregistered or unserved runner label does not fail a job; it queues
    until somebody notices, which is how a release workflow stays inert while
    looking healthy.
    """
    workflow = _workflow()
    lines = [
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith("runs-on:") and not line.strip().startswith("#")
    ]

    assert lines, "the workflow declares no runner"
    assert all(line == "runs-on: ubuntu-latest" for line in lines), lines
    assert "self-hosted" not in workflow
    assert "guild-ai-stp" not in workflow
