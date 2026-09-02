"""The deployment contract this repository publishes and this repository runs.

Split out of the private working copy's `test_deploy_hardening.py` when the
deployment source became the public repository (`ADR-0109`). What stayed behind
asserts a runner fleet that only that working copy has; what is here asserts the
promotion workflow and the host-side deployer, both of which are published — and
must therefore be provable from the tree that actually deploys.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from deploy import verify_public

#: Only the tree that promotes carries this workflow. The private working copy
#: stopped promoting under `ADR-0109`, and asserting a file it must not have
#: would fail there for the right reason but the wrong outcome. The property
#: that matters for that tree is the opposite one, and it is asserted in
#: `test_deploy_hardening.py`: it must hold no deployment workflow at all.
#: Where the workflows this tree runs live. The working copy runs none of its
#: own since `ADR-0110`, so what it holds is the overlay it publishes; the built
#: tree holds those same files as its actual gate. One resolution, stated once.
_OVERLAY = Path("release_scripts/public_overlay/.github/workflows")
WORKFLOWS = _OVERLAY if _OVERLAY.is_dir() else Path(".github/workflows")

DEPLOY_WORKFLOW = WORKFLOWS / "deploy.yml"


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

    # Write is granted to the job that moves the ref and to nothing else. A
    # workflow-wide write would hand it to the proof job, which only reads.
    assert "permissions:\n  contents: read" in workflow
    assert "permissions:\n      contents: write" in workflow
    assert "permissions:\n  contents: write" not in workflow

    # The event and branch are conditions on the job, not only tests inside a
    # `run`. A static analyser cannot see the shell, so an edit dropping the
    # script checks would silently promote a pull-request run; as a job
    # condition the same edit skips the job instead.
    assert "github.event.workflow_run.event == 'push'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow

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
    gate = (WORKFLOWS / "check.yml").read_text(encoding="utf-8")

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
    assert "--preserve-permissions" in script
    assert "chmod u+x" in script
    assert "deploy/load-apparmor.sh" in script
    assert 'AI_STP_REMOTE_ROOT="${root}"' in script
    assert "--exclude '.deploy-state' --exclude '.backups'" in script
    assert "--exclude '.env.prod'" in script
    assert "--exclude '.deploy-env'" in script
    assert "./deploy/run.sh" in script
    assert "./deploy/verify.sh" in script
    # Ninety-four extracted commits used four gigabytes. The live tree and the
    # rollback commit are the only extracts that answer a question. An already-
    # current tick still has to prune, because that is the path that never
    # rsyncs a newer script onto the host.
    assert 'prune_release_archives "${candidate}" "${previous_commit}"' in script
    assert 'prune_release_archives "${candidate}" "${current}"' in script
    assert script.find('prune_release_archives "${candidate}" "${previous_commit}"') < (
        script.find("pull_deploy_already_current")
    )
    assert script.find('prune_release_archives "${candidate}" "${current}"') > script.find(
        "./deploy/verify.sh"
    )

    # The source is this repository, fetched anonymously (`ADR-0109`). A private
    # default here would be invisible until a host rebuilt its mirror and then
    # quietly deployed from somewhere nobody can read.
    assert "https://github.com/ai-engineers-guild/ai-stp.git" in script
    assert "git@github.com:" not in script

    # Set once at creation, `${repository}` described the mirror's first fetch
    # and nothing after it, so changing the source changed nothing. This is the
    # assertion that would have caught it.
    assert 'remote set-url origin "${repository}"' in script
    # A host user's optional `gh auth setup-git` helper must not turn the
    # public fetch into an authenticated request. A stale token produced HTTP
    # 401 while curl and a helper-free fetch both read the same public ref.
    fetch = script.split("fetch --quiet --no-tags origin", maxsplit=1)[0].rsplit("\n", maxsplit=2)
    fetch_prefix = "\n".join(fetch)
    assert "GIT_TERMINAL_PROMPT=0" in fetch_prefix
    assert "-c credential.helper=" in fetch_prefix

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


def test_required_content_import_secret_is_checked_before_any_deploy_effect() -> None:
    """A missing importer token must leave the currently healthy web running.

    The importer itself fails closed without the token, but web waits for that
    one-shot. Discovering the missing value after ``compose up`` left web in
    ``Created`` and production on 502 while the next minute-timer rebuilt every
    image. The deployer owns the ordering: validate the precondition before it
    records progress, builds, migrates or recreates anything.
    """
    deploy = Path("deploy/deploy.sh").read_text(encoding="utf-8")
    preflight = 'require_env_value "AI_STP_CONTENT_IMPORT_TOKEN"'
    assert preflight in deploy
    assert deploy.index(preflight) < deploy.index('record_deploy_stage "${COMMIT}" "started"')
    assert deploy.index(preflight) < deploy.index("compose build")

    library = Path("deploy/lib.sh").read_text(encoding="utf-8")
    helper = library.split("require_env_value()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[0]
    assert "source " not in helper
    assert "grep -Eq" in helper


def test_deployment_verification_observes_the_service_that_gates_publication() -> None:
    """A green deploy has to mean the worker is current, not only reachable.

    The worker serves no HTTP, so the health probes cannot see it — and it is
    the service that runs every publication's safety scan. A deployment that
    left it on the previous image reported success while nothing it decided had
    changed, which is how a fixed scanner went on refusing a corpus.

    `AI_STP_API_GIT_COMMIT` cannot stand in for this. It is an environment
    variable the API echoes back, so it describes the deployment attempt rather
    than the code any container is actually running.
    """
    script = Path("deploy/verify.sh").read_text(encoding="utf-8")

    assert "compose ps -q worker" in script
    # Running is not current: a container from the previous deployment is
    # running too, and only its image tells the two apart. Asked of the
    # container — `compose config --images worker` ignores the service argument
    # and prints every service's image, so reading its first line compared the
    # worker against `postgres:16` and failed a real deployment.
    # Executable lines only: the comment above the fix names the command it
    # replaced, and that explanation is the reason to keep, not to forbid.
    runnable = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
    assert "compose config --images" not in runnable
    assert "docker inspect -f '{{.Config.Image}}'" in script
    assert "docker inspect -f '{{.Image}}'" in script
    assert ".State.Health.Status" in script
    assert "failed=1" in script.split("worker_id=", maxsplit=1)[1]


def test_a_deployment_check_that_cannot_answer_does_not_stop_the_deployment() -> None:
    """Undetermined is not stale, and this is not a hypothetical.

    The image comparison was written against a command that ignores its service
    argument, so it always compared the wrong two things and always failed. It
    took production down until the deployment was fixed, which is a worse
    outcome than the stale worker it was added to catch.
    """
    script = (Path("deploy/verify.sh")).read_text(encoding="utf-8")
    block = script.split("tag=", maxsplit=1)[1].split('if [[ "${failed}"', maxsplit=1)[0]

    assert 'if [[ -z "${want}" || -z "${have}" ]]; then' in block
    undetermined = block.split('if [[ -z "${want}"', maxsplit=1)[1].split("elif", maxsplit=1)[0]
    assert "failed=1" not in undetermined


def test_deployment_verification_reports_only_declared_probe_origins() -> None:
    """The success line must also work when no legacy deploy environment exists."""
    script = Path("deploy/verify.sh").read_text(encoding="utf-8")
    success = script.splitlines()[-1]

    assert "${API_BASE}" in success
    assert "${WEB_BASE}" in success
    assert "${BASE}" not in success


def test_edge_routes_the_google_compatibility_callback_to_the_api() -> None:
    config = Path("deploy/nginx/ai-stp.conf.template").read_text(encoding="utf-8")
    block = config.split("location = /api/auth/callback/google", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]

    assert "proxy_pass http://@@API_BIND@@" in block


def test_no_workflow_carries_a_deployment_credential_or_reaches_the_target() -> None:
    """Untrusted pull-request code and the deployment share no job at all.

    The `ADR-0046` split used to be asserted against one gate on one fleet.
    Nothing about it depended on that fleet: what it protects is that a
    workflow running a stranger's code holds nothing that can reach the target,
    and that no job is scheduled onto the target itself.
    """
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        executable = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in ("AI_STP_DEPLOY", "known_hosts", "runs-on: ai-stp-prod", "self-hosted"):
            assert forbidden not in executable, f"{path.name}: {forbidden}"


def test_the_images_resolve_the_lockfile_with_the_uv_every_gate_installs() -> None:
    """What production installs with must be what CI proved it with.

    The images used to take `ghcr.io/astral-sh/uv:0.9`. That tag moves, so two
    builds of the same commit could resolve `uv.lock` with different releases —
    the image was not reproducible from the commit, which `SPEC-024` requires.
    It was also a major line away from the `uv` every gate installs, so the
    resolver that produced the lockfile and the one that consumed it were never
    the same program.

    Both halves are asserted because fixing one without the other leaves a
    reproducible image resolving with something nothing tested.
    """
    # The bootstrap used to be `pip install "uv==X"`, and the version was read
    # out of that string. It is now the first argument to `install-uv.sh`,
    # either a literal or the workflow's own `UV_VERSION`, so both shapes are
    # resolved here — reading only the old one would have found no version at
    # all and passed the emptiness check by accident.
    installed: set[str] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        declared = re.findall(r'UV_VERSION:\s*"([0-9][^"]*)"', text)
        for argument in re.findall(r'install-uv\.sh"?\s+"([^"]+)"', text):
            if argument == "${UV_VERSION}":
                assert declared, f"{path.name} uses UV_VERSION without declaring it"
                installed.update(declared)
            else:
                installed.add(argument)
    assert installed, "no workflow installs uv"
    assert len(installed) == 1, f"workflows install more than one uv: {sorted(installed)}"
    expected = installed.pop()

    dockerfiles = sorted(Path().glob("Dockerfile*"))
    assert dockerfiles, "no Dockerfile found"
    seen = 0
    for path in dockerfiles:
        executable = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        for reference in re.findall(r"ghcr\.io/astral-sh/uv[^\s]*", executable):
            seen += 1
            assert "@sha256:" in reference, f"{path} takes uv by a moving reference: {reference}"
            assert f":{expected}@" in reference, (
                f"{path} pins uv {reference.split('@')[0]}, gates install uv=={expected}"
            )
    assert seen >= 3, f"expected every image to pin uv, found {seen} references"


def test_platform_evidence_stays_manual_and_can_neither_publish_nor_deploy() -> None:
    """An optional oracle, not a gate, and holding no authority either way."""
    path = WORKFLOWS / "platform-evidence.yml"
    if not path.is_file():
        pytest.skip("this tree carries no platform evidence workflow")
    workflow = path.read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    )

    assert "workflow_dispatch:" in workflow
    assert "on:\n  push:" not in workflow
    for forbidden in ("id-token: write", "attestations: write", "contents: write"):
        assert forbidden not in executable, forbidden


def test_deploy_verification_outlasts_its_own_wait() -> None:
    """A job killed before its wait concludes reports the target as late.

    The `verify-public` comment states the rule itself — the ceiling is "the
    wait below plus checkout and setup", larger than the wait, "so a timeout
    means the job was starved rather than the target being late". Nothing
    checked that the two numbers obeyed it.

    They stopped obeying it the moment the wait was raised. A deployment
    measured at 13m17s pushed `--wait-seconds` to 1500 while
    `timeout-minutes` stayed at 18, so the job was cancelled seven minutes
    before its own wait could finish. Run 32629727961 did exactly that, at
    18m28s, while production had in fact deployed — the red run for a healthy
    deployment that raising the wait was meant to stop.

    Stated as a relationship rather than a number, because the number is a fact
    about how long the host takes to rebuild and will move again. What must
    hold is the order between them.
    """
    workflow = _deploy_workflow()
    # Scoped to the job that waits. Reading the file as a whole finds
    # `promote`'s ceiling first, which bounds a different thing entirely.
    job = workflow.split("\n  verify-public:", 1)
    assert len(job) == 2, "the verification job is no longer named verify-public"
    body = job[1]
    wait = re.search(r"--wait-seconds\s+(\d+)", body)
    assert wait, "verification no longer bounds its wait"
    ceiling = re.search(r"timeout-minutes:\s*(\d+)", body)
    assert ceiling, "the verification job declares no timeout"
    wait_minutes = int(wait.group(1)) / 60
    assert int(ceiling.group(1)) > wait_minutes, (
        f"verify-public is capped at {ceiling.group(1)} minutes but waits "
        f"{wait_minutes:.0f} — it will be cancelled before it can conclude, and "
        "report a healthy deployment as a failure"
    )


def test_both_deploy_jobs_state_the_condition_they_depend_on() -> None:
    """`needs` is not visible to a static analyser, and one job checks out code.

    `promote` already duplicates its event and branch condition in a job `if`,
    with a comment saying why: a later edit that dropped the `test` inside `run`
    would silently start promoting a pull-request run, while the same mistake
    stated as a job condition merely skips.

    `verify-public` checks out `workflow_run.head_sha`. It could never run on a
    fork's pull request — `promote` refuses anything but a push to `main`, and a
    skipped dependency skips its dependents — but CodeQL reported it as an
    untrusted checkout because nothing said so where a scanner could read it.
    Both jobs now state it.
    """
    workflow = _deploy_workflow()
    guard = "github.event.workflow_run.event == 'push'"
    branch = "github.event.workflow_run.head_branch == 'main'"
    assert workflow.count(guard) >= 2, "a job that runs on workflow_run does not state its event"
    assert workflow.count(branch) >= 2, "a job that runs on workflow_run does not state its branch"


def test_the_worker_apparmor_profile_allows_userns_and_is_loaded_before_compose() -> None:
    """Bubblewrap needs a named profile that allows userns. Unconfined does not.

    Ubuntu 24.04 sets kernel.apparmor_restrict_unprivileged_userns=1. A worker
    started under docker-default (or apparmor=unconfined) cannot create the
    user namespace, safety_readiness stays false, and REQUIRE_BWRAP turns every
    external scanner into exit 126. The profile and the loader are the in-repo
    fix; privileged root and flipping the sysctl are not.
    """
    profile = Path("deploy/apparmor/ai-stp-worker").read_text(encoding="utf-8")
    loader = Path("deploy/load-apparmor.sh").read_text(encoding="utf-8")
    deploy = Path("deploy/deploy.sh").read_text(encoding="utf-8")
    rules = "\n".join(line for line in profile.splitlines() if not line.lstrip().startswith("#"))

    assert "profile ai-stp-worker" in rules
    assert "userns," in rules
    assert "unconfined" not in rules
    assert "privileged: true" not in Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "apparmor_parser" in loader
    assert "NoNewPrivileges" in loader
    assert "--privileged" in loader
    assert "nsenter" in loader
    assert "/etc/apparmor.d/ai-stp-worker" in loader

    assert "load-apparmor.sh" in deploy
    assert deploy.find("load-apparmor.sh") < deploy.find("compose up -d api worker")
    assert "compose rm -fs content-import" in deploy
    assert "compose up -d api worker content-import web docs" in deploy
    assert deploy.find("compose rm -fs content-import") < deploy.find(
        "compose up -d api worker content-import web docs"
    )
    listed = subprocess.check_output(
        ["git", "ls-files", "-s", "--", "deploy/load-apparmor.sh"],
        text=True,
    )
    assert listed.startswith("100755 "), listed


def test_a_deploy_overtaken_by_a_newer_one_is_not_a_failure() -> None:
    """Being superseded is the deployment succeeding, and it was reported red.

    Measured on 2026-08-29, run `33220211048`. Three commits were pushed within
    twenty minutes, so three deploy runs were in flight against one host. The
    ref is monotonic, the host deploys the newest, and each job then waits for
    the host to record **its own** SHA. `ba0546e` retried 106 times against a
    host that was already serving `40f9850` — a commit containing it — and
    failed.

    That is failure by construction: any run overtaken by a newer one must go
    red, whatever the host does. The property being defended is *the promoted
    commit reached the target*, and a descendant carries it; the check asked the
    narrower question of exact identity, which is the same shape as every other
    defect this week.

    So the caller decides what counts, and the default stays exact equality: the
    workflow supplies a predicate backed by `git merge-base --is-ancestor`, and
    nothing here silently accepts an unrelated SHA.
    """
    older = "a" * 40
    newer = "b" * 40

    def fetch(url: str, _limit: int) -> tuple[int, bytes]:
        if url.endswith("/health/live"):
            payload: dict[str, object] = {"schema_version": 1, "status": "alive"}
        elif url.endswith("/health/ready"):
            payload = {"schema_version": 1, "status": "ready"}
        elif url.endswith("/v1/system/version"):
            payload = {
                "schema_version": 1,
                "git_commit": newer,
                "schema_revision": "0005",
                "environment": "prod",
            }
        else:
            return 200, b"web"
        return 200, json.dumps(payload).encode()

    # Overtaken, and the caller can say so.
    verify_public.verify(
        "https://nddev.asia",
        expected_commit=older,
        expected_schema="0005",
        expected_environment="prod",
        fetch=fetch,
        commit_accepted=lambda deployed: deployed == newer,
    )

    # Unrelated is still a failure, and the default is still exact equality.
    with pytest.raises(verify_public.VerificationError, match="deployed git_commit"):
        verify_public.verify(
            "https://nddev.asia",
            expected_commit=older,
            expected_schema="0005",
            expected_environment="prod",
            fetch=fetch,
            commit_accepted=lambda _deployed: False,
        )
    with pytest.raises(verify_public.VerificationError, match="deployed git_commit"):
        verify_public.verify(
            "https://nddev.asia",
            expected_commit=older,
            expected_schema="0005",
            expected_environment="prod",
            fetch=fetch,
        )


def test_ancestry_is_asked_of_github_because_the_clone_cannot_answer() -> None:
    """The repair that would have been correct and unreachable.

    `actions/checkout` in `deploy.yml` is shallow and pinned to the promoted
    SHA, so the commit that overtook it — pushed after this job started — is not
    in the clone. `git merge-base --is-ancestor` would answer "no" for exactly
    the case this recognises, and the fix would have read as done while changing
    nothing. So the question goes to the graph's owner.
    """
    calls: list[str] = []

    def compare(status: str) -> Callable[[str, int], tuple[int, bytes]]:
        def fetch(url: str, _limit: int) -> tuple[int, bytes]:
            calls.append(url)
            return 200, json.dumps({"status": status}).encode()

        return fetch

    older, newer = "a" * 40, "b" * 40
    for status, expected in (
        ("ahead", True),
        ("identical", True),
        ("behind", False),
        ("diverged", False),
    ):
        assert (
            verify_public.contains(
                older,
                newer,
                repository="owner/repo",
                fetch=compare(status),  # type: ignore[arg-type]
            )
            is expected
        ), status

    assert calls[0] == f"https://api.github.com/repos/owner/repo/compare/{older}...{newer}"

    # Equality never asks anything.
    before = len(calls)
    assert verify_public.contains(older, older, repository="owner/repo", fetch=compare("behind"))
    assert len(calls) == before

    # A transport failure, a non-200 and a malformed SHA all refuse rather than
    # assume: the caller keeps waiting, which is the previous behaviour.
    def exploding(_url: str, _limit: int) -> tuple[int, bytes]:
        raise OSError("no network")

    assert not verify_public.contains(older, newer, repository="owner/repo", fetch=exploding)

    def missing(_url: str, _limit: int) -> tuple[int, bytes]:
        return 404, b"{}"

    assert not verify_public.contains(older, newer, repository="owner/repo", fetch=missing)
    assert not verify_public.contains(older, "not-a-sha", repository="owner/repo", fetch=missing)


def test_the_deploy_workflow_names_the_repository_ancestry_is_asked_of() -> None:
    """The predicate is only reachable if the workflow supplies its input.

    Read through `_deploy_workflow`, which is where this file resolves that path
    once — overlay first, then the tree's own, and skip where neither exists. I
    wrote `Path(".github/workflows/deploy.yml")` here instead and it failed in
    the copy that holds no workflows: a second resolution of a fact this module
    states at the top, in the same session spent removing exactly that.
    """
    assert "--repository" in _deploy_workflow()


def test_the_overtake_comparison_is_bounded_for_a_busy_repository() -> None:
    """The bound that failed a healthy deployment, sized by measurement.

    `verify-public` asks GitHub whether a newer commit overtook the one it is
    verifying. That response carries every changed file between the two refs,
    so its size tracks how busy the repository was and nothing about the
    deployment — and on a day with a 234-file sync it reached 1.1 MiB against
    the shared 64 KiB bound, failing a run whose target was serving correctly.

    Raising it is the fix rather than removing it: a comparison this side does
    not control the size of still must not read without a limit. What is
    asserted here is that the two bounds are separate and that the comparison's
    is the larger, because a single shared number is what made a healthy deploy
    look broken.
    """
    from deploy import verify_public

    assert verify_public.MAX_COMPARE_BYTES > verify_public.MAX_JSON_BYTES
    # Headroom over the largest response observed on this repository, not a
    # round number chosen for looking generous.
    assert verify_public.MAX_COMPARE_BYTES >= 4 * 1024 * 1024
    # And still a bound: an unbounded read is what this whole limit exists for.
    assert verify_public.MAX_COMPARE_BYTES < 64 * 1024 * 1024
