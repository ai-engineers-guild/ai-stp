"""The deployment contract this repository publishes and this repository runs.

Split out of the private working copy's `test_deploy_hardening.py` when the
deployment source became the public repository (`ADR-0109`). What stayed behind
asserts a runner fleet that only that working copy has; what is here asserts the
promotion workflow and the host-side deployer, both of which are published — and
must therefore be provable from the tree that actually deploys.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: Only the tree that promotes carries this workflow. The private working copy
#: stopped promoting under `ADR-0109`, and asserting a file it must not have
#: would fail there for the right reason but the wrong outcome. The property
#: that matters for that tree is the opposite one, and it is asserted in
#: `test_deploy_hardening.py`: it must hold no deployment workflow at all.
DEPLOY_WORKFLOW = Path(".github/workflows/deploy.yml")


def _deploy_workflow() -> str:
    if not DEPLOY_WORKFLOW.is_file():
        pytest.skip("this tree does not promote a deployment ref (ADR-0109)")
    return DEPLOY_WORKFLOW.read_text(encoding="utf-8")


def test_the_deploy_workflow_keeps_the_guarantees_it_inherited() -> None:
    """Green CI promotes one monotonic ref; no Actions job reaches production."""
    workflow = _deploy_workflow()
    # Comments explain why SSH is gone, so the word is legitimate there. What
    # must not contain it is the part that runs.
    executable = "\n".join(
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    )

    # No key, no host, no user, no pinned identity: nothing dials anywhere.
    for forbidden in ("ssh", "AI_STP_DEPLOY", "known_hosts", "rsync -az -e"):
        assert forbidden not in executable, forbidden

    # The production host is not a runner and must never be addressed as one.
    assert "runs-on: ai-stp-prod" not in executable
    assert "self-hosted" not in executable

    # The exact commit `check` proved, not whatever `main` points at now.
    assert "HEAD_SHA: ${{ github.event.workflow_run.head_sha }}" in workflow
    assert workflow.count("ref: ${{ github.event.workflow_run.head_sha }}") == 1
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert 'test "${EVENT}" = "push"' in workflow
    assert 'test "${BRANCH}" = "main"' in workflow

    assert executable.count("persist-credentials: false") == 1
    assert "permissions:\n  contents: write" in workflow
    assert "refs/heads/deploy/prod" in workflow
    assert "-F force=false" in workflow

    # The public route is proved from somewhere that is not the host, and
    # against the one environment's real name (`ADR-0086`). A check that only
    # runs where the service runs cannot tell "up" from "up for me".
    assert "deploy/verify_public.py" in workflow
    assert "--expected-environment prod" in workflow
    assert "needs: promote" in executable

    # A deployment interrupted between transfer and health check leaves a state
    # no verdict describes.
    assert "cancel-in-progress: false" in workflow

    # And the group belongs to the job that promotes, not to the workflow.
    # Shared, it let an observation block a deployment: a `verify-public` still
    # waiting for a worker held the group for thirty-seven minutes while the
    # next deployment queued behind it. Nothing `verify-public` does needs
    # serialising — it only reads a public origin.
    header, jobs = workflow.split("\njobs:\n", maxsplit=1)
    promote, verify = jobs.split("\n  verify-public:\n", maxsplit=1)
    assert "concurrency:" not in header
    assert "group: deploy-promotion" in promote
    assert "concurrency:" not in verify


def test_a_manually_requested_check_answers_but_does_not_ship() -> None:
    """`workflow_dispatch` on the gate must not become a deployment button.

    The gate gained manual dispatch because during a placement outage there was
    no way to ask for a verdict except an empty commit, which lies in the
    history about what changed. Asking whether the tree is green is not the same
    as asking for it to ship, and only the source check keeps them apart.
    """
    deploy = _deploy_workflow()
    gate = Path(".github/workflows/check.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in gate
    # The deployment refuses anything whose source was not a push to `main`, so
    # a dispatched check produces a verdict and nothing else.
    assert 'test "${EVENT}" = "push"' in deploy
    assert "EVENT: ${{ github.event.workflow_run.event }}" in deploy
    assert "workflow_dispatch" not in "\n".join(
        line for line in deploy.splitlines() if not line.lstrip().startswith("#")
    )


def test_target_side_deployer_preserves_the_host_state_and_monotonicity() -> None:
    script = Path("deploy/pull-deploy.sh").read_text(encoding="utf-8")

    assert "+${deploy_ref}:refs/remotes/origin/deploy/prod" in script
    assert "merge-base --is-ancestor" in script
    assert 'git --git-dir="${mirror}" archive' in script
    assert 'AI_STP_REMOTE_ROOT="${root}"' in script
    assert "--exclude '.deploy-state' --exclude '.backups'" in script
    assert "--exclude '.env.prod'" in script
    assert "--exclude '.deploy-env'" in script
    assert "./deploy/run.sh" in script
    assert "./deploy/verify.sh" in script

    # The source is this repository, fetched anonymously (`ADR-0109`). A private
    # default here would be invisible until a host rebuilt its mirror and then
    # quietly deployed from somewhere nobody can read.
    assert "https://github.com/ai-engineers-guild/ai-stp.git" in script
    assert "git@github.com:" not in script

    # Set once at creation, `${repository}` described the mirror's first fetch
    # and nothing after it, so changing the source changed nothing. This is the
    # assertion that would have caught it.
    assert 'remote set-url origin "${repository}"' in script

    service = Path("deploy/ai-stp-pull-deploy.service").read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in service.splitlines() if not line.lstrip().startswith("#")
    )
    assert "User=ubuntu" in service
    assert "StateDirectory=ai-stp-deployer" in service
    assert "AI_STP_ROOT=/home/ubuntu/ai_stp" in service
    assert "AI_STP_PULL_STATE_ROOT=/var/lib/ai-stp-deployer" in service

    # An anonymous fetch needs no identity, and the unit must not acquire one
    # back by habit: a credential here would be a deployment path that the
    # public history cannot account for.
    for forbidden in ("GIT_SSH_COMMAND", "IdentityFile", "ai-stp-prod-pull"):
        assert forbidden not in executable, forbidden
    assert not Path("deploy/ai-stp-pull-ssh.conf").exists()

    # Hardening that a later edit must not quietly drop.
    for directive in ("NoNewPrivileges=true", "PrivateTmp=true", "ProtectSystem=strict"):
        assert directive in service, directive
