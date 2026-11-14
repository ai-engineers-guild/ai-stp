"""The deployment contract this repository publishes and this repository runs.

This tree is the public repository and the deployment source (`ADR-0109`,
`ADR-0110`): it asserts the promotion workflow and the host-side deployer, both
of which must be provable from the tree that actually deploys.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml
from deploy import verify_public

#: Where the workflows this tree runs live.
WORKFLOWS = Path(".github/workflows")

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

    # Execute only the dispatcher's own SHA after it matches the admitted source.
    # A run-output/input SHA must not select privileged executable code.
    jobs = yaml.safe_load(workflow)["jobs"]
    for name in ("promote", "verify-public"):
        checkout = next(
            step
            for step in jobs[name]["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": False}
    assert 'test "${GITHUB_SHA}" = "${head}"' in workflow
    assert "HEAD_SHA: ${{ steps.source.outputs.head_sha }}" in workflow
    assert '.event == "push" and .head_branch == "dev"' in workflow

    assert executable.count("persist-credentials: false") == 2

    # Write is scoped to delivery and its publisher. A workflow-wide write
    # would hand it to the public proof job, which only reads.
    assert "permissions:\n  contents: read" in workflow
    assert "permissions:\n      contents: write" in workflow
    assert "permissions:\n  contents: write" not in workflow

    # Delivery has no fork-triggerable event. Manual dispatch still requires
    # the exact successful push-to-Dev source before privileged checkout.
    assert set(yaml.safe_load(workflow)[True]) == {"workflow_dispatch"}
    assert "github.event_name == 'workflow_dispatch'" in jobs["promote"]["if"]
    assert "github.ref == 'refs/heads/dev'" in jobs["promote"]["if"]

    controller = Path("release_scripts/source_promotion.py").read_text()
    assert "refs/heads/deploy/prod" in controller
    assert '"force": False' in controller
    assert '"force": True' not in controller
    assert any(
        step.get("with", {}).get("recipe") == "ci-delivery-promote"
        for step in jobs["promote"]["steps"]
    )

    # The public route is proved from somewhere that is not the host, and
    # against the one environment's real name (`ADR-0086`). A check that only
    # runs where the service runs cannot tell "up" from "up for me".
    assert "deploy/verify_public.py" in workflow
    assert "--expected-environment prod" in workflow
    assert "needs: promote" in executable
    assert "needs.promote.outputs.deployed == 'true'" in jobs["verify-public"]["if"]

    # The docs site is the third published service, on its own hostname. Its
    # origin is a repository variable like the main one, and the job fails on
    # an unset variable rather than quietly skipping the probe.
    assert "--docs-origin" in workflow
    assert "vars.AI_STP_DOCS_ORIGIN" in workflow
    assert 'test -n "${DOCS_ORIGIN}"' in workflow

    runbook = Path("docs/operations/runbooks/deploy.md").read_text(encoding="utf-8")
    assert "AI_STP_PUBLIC_ORIGIN" in runbook
    assert "AI_STP_DOCS_ORIGIN" in runbook
    assert "AI_STP_CATALOG_CURSOR_SIGNING_SECRET" in runbook
    assert "AI_STP_CATALOG_CURSOR_SECRET" not in runbook

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
    # A manual check has no delivery authority. Manual repair names an existing
    # push-to-Dev source run and goes through the same admission controller.
    assert '.event == "push" and .head_branch == "dev"' in deploy
    events = yaml.safe_load(deploy)[True]
    assert set(events) == {"workflow_dispatch"}
    assert set(events["workflow_dispatch"]["inputs"]) == {"source_run_id"}


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
    # GitHub's HTTP/2 upload-pack POST returned 401 from the production host
    # while the same anonymous request over HTTP/1.1 and the public archive
    # endpoint both answered. Keep this transport fact local to the fetch.
    assert "-c http.version=HTTP/1.1" in fetch_prefix

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


@pytest.mark.parametrize("deploy_exit", [0, 23])
def test_pull_deploy_never_collects_daemon_objects(tmp_path: Path, deploy_exit: int) -> None:
    """Exercise both attempt outcomes without a Docker daemon or a live deployment."""
    candidate = "a" * 40
    previous = "b" * 40
    application = tmp_path / "application"
    state = tmp_path / "pull-state"
    tools = tmp_path / "tools"
    tools.mkdir()
    (state / "repository.git").mkdir(parents=True)
    release = state / "releases" / candidate / "deploy"
    release.mkdir(parents=True)
    (application / ".deploy-state").mkdir(parents=True)
    (application / ".deploy-state/current").write_text(f"git_commit={previous}\n")
    (application / ".env.prod").write_text("owned host sentinel\n")
    calls = tmp_path / "docker-calls.jsonl"

    def executable(path: Path, body: str) -> None:
        path.write_text(body)
        path.chmod(0o755)

    executable(
        tools / "git",
        f"#!{sys.executable}\nimport sys\nif 'rev-parse' in sys.argv: print('{candidate}')\n",
    )
    executable(
        tools / "rsync",
        f"#!{sys.executable}\nimport shutil, sys\n"
        "shutil.copytree(sys.argv[-2], sys.argv[-1], dirs_exist_ok=True)\n",
    )
    executable(
        tools / "docker",
        f"#!{sys.executable}\nimport json, os, sys\n"
        "with open(os.environ['AI_STP_TEST_DOCKER_CALLS'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n",
    )
    for name in ["pull-deploy.sh", "deploy.sh", "lib.sh", "load-apparmor.sh", "mark-transfer.sh"]:
        executable(release / name, "#!/bin/sh\nexit 0\n")
    executable(release / "run.sh", f"#!/bin/sh\nprintf run > run.called\nexit {deploy_exit}\n")
    executable(release / "verify.sh", "#!/bin/sh\nprintf verify > verify.called\n")
    result = subprocess.run(
        ["bash", str(Path("deploy/pull-deploy.sh").resolve())],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            "AI_STP_ROOT": str(application),
            "AI_STP_PULL_STATE_ROOT": str(state),
            "AI_STP_PULL_REPOSITORY": "https://example.invalid/ai-stp.git",
            "AI_STP_TEST_DOCKER_CALLS": str(calls),
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == deploy_exit, result.stdout + result.stderr
    assert (application / "run.called").is_file()
    assert (application / "verify.called").exists() is (deploy_exit == 0)
    assert not calls.exists(), calls.read_text() if calls.exists() else ""
    assert (application / ".env.prod").read_text() == "owned host sentinel\n"
    if deploy_exit == 0:
        assert f"pull_deploy_complete commit={candidate}" in result.stdout
    else:
        assert "pull_deploy_complete" not in result.stdout


def test_required_secrets_are_checked_before_any_deploy_effect() -> None:
    """A missing or placeholder secret must leave the healthy release serving.

    The importer itself fails closed without the token, but web waits for that
    one-shot. Discovering the missing value after ``compose up`` left web in
    ``Created`` and production on 502 while the next minute-timer rebuilt every
    image. The deployer owns the ordering: validate the precondition before it
    records progress, builds, migrates or recreates anything — for every value
    a serving container refuses to boot without, not only the token.
    """
    deploy = Path("deploy/deploy.sh").read_text(encoding="utf-8")
    library = Path("deploy/lib.sh").read_text(encoding="utf-8")
    preflight = library.split("require_deploy_env()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[0]
    required = [
        "AI_STP_API_ENVIRONMENT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "AI_STP_DB_URL",
        "AI_STP_STORAGE_ENDPOINT",
        "AI_STP_STORAGE_ACCESS_KEY_ID",
        "AI_STP_STORAGE_SECRET_ACCESS_KEY",
        "AI_STP_STORAGE_ARTIFACT_BUCKET",
        "AI_STP_STORAGE_ASSET_BUCKET",
        "RUSTFS_ACCESS_KEY",
        "RUSTFS_SECRET_KEY",
        "AI_STP_CONTENT_IMPORT_TOKEN",
    ]
    value_block = preflight.split("for required_name in", maxsplit=1)[1].split("done", maxsplit=1)[
        0
    ]
    for name in required:
        assert name in value_block, name
    secret_block = preflight.split("for required_secret in", maxsplit=1)[1].split(
        "done", maxsplit=1
    )[0]
    for name in (
        "AI_STP_AUTH_SECRET_KEY",
        "AI_STP_CATALOG_CURSOR_SIGNING_SECRET",
        "AI_STP_SESSION_SECRET",
    ):
        assert name in secret_block, name
    origin_block = preflight.split("for required_origin in", maxsplit=1)[1].split(
        "done", maxsplit=1
    )[0]
    for name in (
        "NEXT_PUBLIC_APP_URL",
        "AI_STP_USER_DOCS_URL",
        "AI_STP_AUTH_PUBLIC_BASE_URL",
    ):
        assert name in origin_block, name
    # The API pair and the store pair must agree, and optional credentials that
    # were copied out of the example file are worse than absent ones.
    assert "require_env_pair_equal AI_STP_STORAGE_ACCESS_KEY_ID RUSTFS_ACCESS_KEY" in preflight
    assert "require_env_pair_equal AI_STP_STORAGE_SECRET_ACCESS_KEY RUSTFS_SECRET_KEY" in preflight
    assert "AI_STP_WORKER_GITHUB_TOKEN" in preflight
    assert "refuse_env_placeholder" in preflight
    assert 'require_env_value "${required_name}"' in preflight
    assert 'require_env_secret "${required_secret}"' in preflight
    assert 'require_env_public_origin "${required_origin}"' in preflight
    # The deployer calls the shared contract before recording progress,
    # building, migrating or recreating anything.
    assert deploy.index("require_deploy_env") < deploy.index(
        'record_deploy_stage "${COMMIT}" "started"'
    )
    assert deploy.index("require_deploy_env") < deploy.index("compose build")
    helper = library.split("require_env_value()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[0]
    assert "source " not in helper
    assert "grep -Eq" in helper
    assert "*CHANGE_ME*" in helper
    secret = library.split("require_env_secret()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[0]
    assert "CHANGE_ME*" in secret
    assert "-ge 32" in secret
    assert "${value}" not in secret.split("die", maxsplit=1)[-1]
    origin = library.split("require_env_public_origin()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[
        0
    ]
    assert "*example.invalid*" in origin
    assert "*localhost*" in origin
    pair = library.split("require_env_pair_equal()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[0]
    assert "env_file_value" in pair
    # Values are compared through command substitution, never echoed: no
    # output statement may interpolate the read value or the file lookup.
    for fn in ("require_env_value", "require_env_secret", "require_env_pair_equal"):
        body = library.split(f"{fn}()", maxsplit=1)[1].split("\n}\n", maxsplit=1)[0]
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(("die ", "echo ", "printf ")):
                assert "${value}" not in line, (fn, line)
                assert "$(env_file_value" not in line, (fn, line)


def test_storage_cutover_and_backups_fail_closed() -> None:
    deploy = Path("deploy/deploy.sh").read_text(encoding="utf-8")
    backup = Path("deploy/backup.sh").read_text(encoding="utf-8")
    restore = Path("deploy/restore.sh").read_text(encoding="utf-8")

    cutover = "python -m ai_stp_platform.storage.migrate"
    assert cutover in deploy
    assert deploy.index("compose run --rm --no-deps migrate") < deploy.index(cutover)
    assert deploy.index(cutover) < deploy.index("compose run --rm --no-deps seed")

    verifier = "python -m ai_stp_platform.storage.verify"
    assert verifier in backup
    assert backup.index(verifier) < backup.index("sh -c 'pg_dump")
    assert verifier in restore
    assert cutover in restore
    assert restore.index(cutover) < restore.index(verifier)
    assert restore.index(verifier) < restore.index("start_serving_services")

    assert "require_cmd findmnt" in backup
    assert 'ROOT_MOUNT="$(findmnt -n -o TARGET -T "${AI_STP_ROOT}")"' in backup
    assert 'BACKUP_MOUNT="$(findmnt -n -o TARGET -T "${AI_STP_BACKUP_DIR}")"' in backup
    assert "off_host_backup_mount_required" in backup
    assert "AI_STP_ALLOW_LOCAL_BACKUP" in backup


@pytest.mark.skipif(os.name == "nt", reason="the deploy scripts are bash on a Linux host")
def test_the_serving_bring_up_replaces_each_service_once_in_order(tmp_path: Path) -> None:
    """Observed on 2026-10-05: the old bring-up held api and web stopped for ~65 s.

    `compose up` followed `depends_on` and restarted the exited migrate and seed
    containers after stopping the containers it was recreating. The bring-up now
    runs against a `docker` that only records its arguments: the importer runs
    to completion between api and web, and no one-shot appears at all.
    """
    calls = tmp_path / "calls"
    shim = tmp_path / "bin" / "docker"
    shim.parent.mkdir()
    shim.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >>"$DOCKER_CALLS"\n', encoding="utf-8")
    shim.chmod(0o755)
    compose_file = tmp_path / "deploy" / "compose.prod.yml"
    subprocess.run(
        ["bash", "-c", "source deploy/lib.sh && start_serving_services"],
        check=True,
        env={
            "PATH": f"{shim.parent}:/usr/bin:/bin",
            "DOCKER_CALLS": str(calls),
            "AI_STP_ROOT": str(tmp_path),
        },
    )
    prefix = f"compose -f {compose_file} "
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert all(line.startswith(prefix) for line in recorded), recorded
    assert [line.removeprefix(prefix) for line in recorded] == [
        "up -d --no-deps --wait api",
        "up -d --no-deps --wait api-standby",
        "rm -fs content-import",
        "run --rm --no-deps content-import",
        "up -d --no-deps --wait web docs",
        "up -d --no-deps --wait web-standby docs-standby",
        "up -d --no-deps --wait osv-refresh clamav-refresh",
        "up -d --no-deps --wait worker",
    ]


@pytest.mark.skipif(os.name == "nt", reason="the deploy scripts are bash on a Linux host")
@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("transfer_started", "level=info msg=transfer_handoff commit=" + "a" * 40),
        ("migrated", "level=warning msg=recovering_interrupted_deploy"),
        (None, None),
    ],
)
def test_the_handoff_marker_is_not_reported_as_an_interruption(
    tmp_path: Path, marker: str | None, expected: str | None
) -> None:
    """Every deploy of 2026-10-05 warned `recovering_interrupted_deploy`.

    The pull deployer marks each transfer before rsync, and deploy.sh read that
    marker for the very commit it was deploying as an interrupted run.
    """
    state = tmp_path / "state"
    state.mkdir()
    if marker is not None:
        (state / "in-progress").write_text(
            f"git_commit={'a' * 40}\nstage={marker}\n", encoding="utf-8"
        )
    finished = subprocess.run(
        ["bash", "-c", f"source deploy/lib.sh && report_in_progress_marker {'a' * 40}"],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "AI_STP_STATE_DIR": str(state)},
    )
    if expected is None:
        assert finished.stderr == ""
    else:
        assert expected in finished.stderr, finished.stderr


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
    # The platform image Compose recorded, against the tag's platform image: an
    # index-only rebuild left a current worker reported stale for two days.
    assert "com.docker.compose.image" in script
    assert 'docker image inspect --platform "${platform}"' in script
    assert "docker inspect -f '{{.Image}}'" not in runnable
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
    assert "${DOCS_BASE}" in success
    assert "${BASE}" not in success

    # The docs site is published beside web and api; a verify that does not
    # probe it reports green for a host that serves a broken docs hostname.
    assert "AI_STP_VERIFY_DOCS_URL" in script
    assert '"${DOCS_BASE}/"' in script

    # Compose reports the web container started before its first HTTP accept.
    # Two real rolls hit connection reset/empty reply at this exact probe and
    # were marked failed although the same URL answered moments later.
    web_probe = script.split('web="$(', maxsplit=1)[1].split(')"', maxsplit=1)[0]
    assert "--retry-all-errors" in web_probe
    assert "--retry-max-time" in web_probe


def test_edge_refuses_malformed_server_action_probes() -> None:
    """A one-character next-action header is a scanner, not a Next.js action.

    Production logged `Server Reference ID did not match the expected format.
    Received "y"` for a POST the web container then treated as a server error.
    Real action ids are long hashed references; 1-9 characters never is one.
    """
    config = Path("deploy/nginx/ai-stp.conf.template").read_text(encoding="utf-8")
    assert "http_next_action" in config
    assert 'if ($method_next_action ~ "^POST:.{1,9}$")' in config
    assert "return 400;" in config
    catch_all = config.split("location / {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assert "proxy_pass http://ai_stp_web_@@SITE@@" in catch_all


def test_edge_routes_the_google_compatibility_callback_to_the_api() -> None:
    config = Path("deploy/nginx/ai-stp.conf.template").read_text(encoding="utf-8")
    block = config.split("location = /api/auth/callback/google", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]

    assert "proxy_pass http://ai_stp_api_@@SITE@@" in block


def test_every_edge_upstream_has_a_standby_the_deploy_replaces_second() -> None:
    """A release replaced the only api and web containers and the edge answered 502.

    Each upstream now names the serving container and a backup on its own port,
    nginx moves a refused connection to the other, and the bring-up replaces the
    pair one after the other, so one of them serves throughout a release.
    """
    compose = Path("deploy/compose.prod.yml").read_text(encoding="utf-8")
    lib = Path("deploy/lib.sh").read_text(encoding="utf-8")
    for name, template, standby_bind in [
        ("api", "ai-stp.conf.template", "API_STANDBY_BIND"),
        ("web", "ai-stp.conf.template", "WEB_STANDBY_BIND"),
        ("docs", "ai-stp-docs.conf.template", "DOCS_STANDBY_BIND"),
    ]:
        config = Path("deploy/nginx", template).read_text(encoding="utf-8")
        upstream = config.split(f"upstream ai_stp_{name}_@@SITE@@ {{", maxsplit=1)[1]
        upstream = upstream.split("}", maxsplit=1)[0]
        assert f"server @@{name.upper()}_BIND@@ max_fails=1" in upstream
        assert f"server @@{standby_bind}@@ backup;" in upstream
        assert "proxy_next_upstream error timeout;" in config
        assert f"  {name}-standby:\n    <<: *{name}\n" in compose
        assert f"AI_STP_{standby_bind}" in compose
        bring_up = [line.split() for line in lib.splitlines() if "up -d --no-deps --wait" in line]
        primary = next(i for i, words in enumerate(bring_up) if name in words)
        assert primary < next(i for i, words in enumerate(bring_up) if f"{name}-standby" in words)


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
    installed: set[str] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        declared = re.findall(r'UV_VERSION:\s*["\']([0-9][^"\']*)["\']', text)
        for argument in re.findall(r"^\s+uv-version: (.+)$", text, flags=re.MULTILINE):
            if argument == "${{ env.UV_VERSION }}":
                assert declared, f"{path.name} uses UV_VERSION without declaring it"
                installed.update(declared)
            else:
                installed.add(argument.strip("'\""))
    assert installed, "no workflow installs uv"
    assert len(installed) == 1, f"workflows install more than one uv: {sorted(installed)}"
    expected = installed.pop()

    dockerfiles = sorted(Path("deploy/docker").glob("Dockerfile*"))
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
    assert seen >= 2, f"expected every image to pin uv, found {seen} references"


def test_bun_install_in_an_image_sees_the_patches_it_applies() -> None:
    """`patchedDependencies` the build context cannot see break the deploy.

    `bun install` resolves entries under `patchedDependencies` relative to
    the manifest, so a deps stage copying only `package.json` and `bun.lock`
    fails with "Couldn't find patch file" — the failure the 2026-10-03
    production deploy hit on the braces depth-guard patch: the host pulled
    the promoted ref, the web image refused to build, and every later tick
    failed the same way until the Dockerfile learned to copy `patches/`.

    For every manifest declaring patches, any Dockerfile that copies that
    manifest into the image copies `patches/` — or a directory containing
    it — before the `bun install` that applies them.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    patched = [
        Path(name).parent
        for name in tracked
        if name.endswith("package.json")
        and json.loads(Path(name).read_text(encoding="utf-8")).get("patchedDependencies")
    ]
    # An empty set would make the loop below green while asserting nothing —
    # the exact "absent is not clean" case this suite refuses elsewhere.
    assert patched, "no manifest declares patchedDependencies"

    dockerfiles = [
        path
        for path in sorted(Path("deploy/docker").glob("Dockerfile*"))
        if not path.name.endswith(".dockerignore")
    ]
    assert dockerfiles, "no Dockerfile found"
    for dockerfile in dockerfiles:
        executable = [
            line
            for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        ]
        for directory in patched:
            manifest = f"{directory.as_posix()}/package.json"
            copied = next(
                (
                    index
                    for index, line in enumerate(executable)
                    if line.startswith("COPY ") and manifest in line
                ),
                None,
            )
            if copied is None:
                continue
            installs = next(
                (
                    index
                    for index, line in enumerate(executable[copied:], copied)
                    if "bun install" in line
                ),
                None,
            )
            assert installs is not None, f"{dockerfile} copies {manifest} but never installs it"
            ancestors = {
                parent.as_posix()
                for parent in (directory, *directory.parents)
                if parent.as_posix() not in ("", ".")
            }
            covered = any(
                f"{directory.as_posix()}/patches" in line
                or any(
                    source.rstrip("/") in ancestors or source == "."
                    for source in line.split()[1:-1]
                )
                for line in executable[copied:installs]
                if line.startswith("COPY ")
            )
            assert covered, (
                f"{dockerfile} runs bun install on {manifest} without copying "
                f"{directory.as_posix()}/patches first"
            )


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
    """Dispatch executes only on Dev; preparation cannot claim public deployment."""
    jobs = yaml.safe_load(_deploy_workflow())["jobs"]
    for name in ("promote", "verify-public"):
        assert "github.event_name == 'workflow_dispatch'" in jobs[name]["if"]
        assert "github.ref == 'refs/heads/dev'" in jobs[name]["if"]
    assert "needs.promote.outputs.deployed == 'true'" in jobs["verify-public"]["if"]


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
    assert "privileged: true" not in Path("deploy/compose.prod.yml").read_text(encoding="utf-8")

    assert "apparmor_parser" in loader
    assert "NoNewPrivileges" in loader
    assert "--privileged" in loader
    assert "nsenter" in loader
    assert "/etc/apparmor.d/ai-stp-worker" in loader

    assert "load-apparmor.sh" in deploy
    assert deploy.find("load-apparmor.sh") < deploy.find("start_serving_services")
    listed = subprocess.check_output(
        ["git", "ls-files", "-s", "--", "deploy/load-apparmor.sh"],
        text=True,
    )
    assert listed.startswith("100755 "), listed


def test_a_postgres_major_upgrade_copies_into_its_own_volume_before_bring_up() -> None:
    """SPEC-024 REQ-2419: the old major's volume is the rollback copy.

    A new image on the old data directory refuses to start, and a new image on
    an empty volume starts an empty database that migrate would happily fill.
    The data has to be copied, verified, and only then served, and the copy's
    source must survive the upgrade untouched.
    """
    deploy = Path("deploy/deploy.sh").read_text(encoding="utf-8")
    script = Path("deploy/postgres-major-upgrade.sh").read_text(encoding="utf-8")
    compose = Path("deploy/compose.prod.yml").read_text(encoding="utf-8")
    runnable = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))

    assert "postgres-major-upgrade.sh" in deploy
    assert deploy.find("postgres-major-upgrade.sh") < deploy.find("compose up -d --wait postgres")

    assert "      - pgdata18:/var/lib/postgresql\n" in compose
    assert "\n  pgdata:\n" in compose, "the 16 volume stays declared as the rollback copy"

    assert 'compose stop "${WRITERS[@]}"' in runnable
    assert "--exit-on-error --single-transaction" in runnable
    assert "row_counts" in runnable and "postgres_upgrade_row_counts_differ" in runnable
    # Only the target is ever removed; the legacy volume name is read, never passed on.
    assert re.findall(r"docker volume rm \S+", runnable) == ['docker volume rm "${target_volume}"']
    for line in runnable.splitlines():
        if "legacy_volume}" in line:
            assert not re.search(r"\brm\b|docker volume|\s-v\s", line), line
    listed = subprocess.check_output(
        ["git", "ls-files", "-s", "--", "deploy/postgres-major-upgrade.sh"],
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
        docs_origin="https://docs.nddev.asia",
        fetch=fetch,
        commit_accepted=lambda deployed: deployed == newer,
    )

    # A docs host that does not serve is a deployment defect, not a detail.
    # Match the request host, not a URL prefix: `startswith("https://docs.nddev.asia")`
    # also matches `https://docs.nddev.asia.evil.com`.
    def docs_broken(url: str, _limit: int) -> tuple[int, bytes]:
        if urlsplit(url).hostname == "docs.nddev.asia":
            return 503, b""
        return fetch(url, _limit)

    with pytest.raises(verify_public.VerificationError, match="docs root"):
        verify_public.verify(
            "https://nddev.asia",
            expected_commit=older,
            expected_schema="0005",
            expected_environment="prod",
            docs_origin="https://docs.nddev.asia",
            fetch=docs_broken,
            commit_accepted=lambda deployed: deployed == newer,
        )

    # The same prefix would have 503'd a lookalike host. Production fetches the
    # origin it is given; the stub must not treat another hostname as docs.
    def lookalike_docs(url: str, _limit: int) -> tuple[int, bytes]:
        if urlsplit(url).hostname == "docs.nddev.asia":
            raise AssertionError(f"docs probe leaked onto {url}")
        if urlsplit(url).hostname == "docs.nddev.asia.evil.com":
            return 200, b"docs"
        return fetch(url, _limit)

    verify_public.verify(
        "https://nddev.asia",
        expected_commit=older,
        expected_schema="0005",
        expected_environment="prod",
        docs_origin="https://docs.nddev.asia.evil.com",
        fetch=lookalike_docs,
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
    once and skips where the workflow is absent.
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
