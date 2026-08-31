---
description: "Runbook: reproducible deployment with a web tier, backups, and rollback."
last_verified: "2026-08-29"
---

# Staging deployment

Normative sources: `SPEC-024` (`REQ-2401`..`REQ-2417`), `ADR-0044`,
`ADR-0046`, framework `SPEC-019` / `ADR-0040`. Secrets do not enter the repository
or this runbook—only variable names and commands do.

## Prerequisites

1. An authorized host with Docker Engine, Docker Compose v2, Git, `curl`, `flock`
   (util-linux), and access to the repository clone.
2. Copy `.env.prod.example` → `.env.prod` and fill in the actual secrets
   (at least 32 characters for `AI_STP_SESSION_SECRET` and
   `AI_STP_CATALOG_CURSOR_SECRET`). The file is gitignored.
3. Set `AI_STP_PUBLIC_HOST` to the public name of the deployment host (for ACME), or
   leave `localhost` for a local rehearsal.
4. Pin the target commit: `git checkout <commit>` and
   `git rev-parse HEAD`.

Part of the state belongs to the host rather than the repository: the populated `.env.prod`
with actual secrets and the deployment environment file, which describes the addresses
on which this host publishes the stack and the addresses polled by probes. Both are
created on the host and are not included in the code transfer.

Everything the deployment does not own must be on the transfer exclusion list.
A synchronization with `--delete` once deleted the host environment file; the deployment
then polled the default port, which belonged to a neighboring service,
and reported a readiness timeout for a stack whose containers were all healthy.
The failure looked like an application malfunction, although its cause was the loss of a
host-owned file.

## CI and deployment trust domains

Deployment is automatic and starts **somewhere else**. Its source is the public
`ai-engineers-guild/ai-stp` repository (`ADR-0109`): after a green `check` on
`main`, its `deploy.yml` advances `deploy/prod` via `workflow_run` to the
**exact SHA that `check` verified**, not to the current `main`—another commit
may be merged between verification and deployment. This repository does not
contain a deployment workflow, and `tests/unit/test_deploy_hardening.py`
verifies that it does not.

The connection is initiated from the host to GitHub, not the other way around. The production
host is not an Actions runner: a systemd timer fetches the exact SHA and invokes the local
deployment (`ADR-0103`). Fetching is anonymous over HTTPS—the repository is public,
so the host does not need and does not have a deploy key.

## Host preparation

Advancing the ref does not itself deploy anything: the systemd timer on the host
fetches it. Until this half is installed, `promote` succeeds,
`deploy/prod` moves, and nothing happens—there is no failure anywhere.
That is why the host state is described here rather than left in someone's session history.

Three prerequisites, all on `server-nddev-kazakhstan` under the `ubuntu` user:

1. a repository checkout in `/home/ubuntu/ai_stp`—the `AI_STP_ROOT` value in the unit;
2. both units in `/etc/systemd/system/`;
3. the timer enabled.

The list no longer includes a key or SSH configuration: the source is public and fetching
is anonymous. Outbound port 22 is blocked beyond the fleet as well, which is precisely why
`ssh.github.com:443` used to be required; HTTPS removes that requirement too.

```sh
sudo install -m 0644 deploy/ai-stp-pull-deploy.service /etc/systemd/system/
sudo install -m 0644 deploy/ai-stp-pull-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-stp-pull-deploy.timer
```

Verification is observation, not assumption: the timer must be listed among the
active timers and have fired recently.

```sh
systemctl list-timers ai-stp-pull-deploy.timer
systemctl status ai-stp-pull-deploy.service --no-pager | tail -20
```

systemd creates the state directory `/var/lib/ai-stp-deployer` itself through
`StateDirectory`; it does not need to be created manually, and the unit sets permissions to `0700`.
`pull-deploy.sh` keeps only the extracted current and previous
commits in `releases/`: otherwise, the full archive of every SHA accumulates without an upper bound.

It follows that the deployment owns neither an SSH key, nor a host address,
nor a pinned `known_hosts`: the connection that required them no longer exists.
The only value the workflow takes from the repository is the
`AI_STP_PUBLIC_ORIGIN` variable, an input to `deploy/verify_public.py`.

The separation of trust domains from `ADR-0046` rests on three assertions:

- the executable part of `check.yml` contains none of `secrets.`, `vars.`, `ssh`, or
  `AI_STP_DEPLOY`—code from someone else's pull request runs there;
- no workflow names the `ai-stp-prod` label;
- the source is narrowed twice: `workflow_run` after a completed `check`, plus an explicit
  check for `event == push` and `head_branch == main`.

The first two are checked here, in `tests/unit/test_deploy_hardening.py`; the third is
checked in `tests/unit/test_deploy_contract.py`, which runs in the tree where the
deployment workflow exists and is skipped where it must not exist.

The public route is verified **off** the host: a separate job
`verify-public` on a standard GitHub runner, which needs only outbound
port 443. A check that runs only where the service runs cannot distinguish
"is up" from "is up for me."

The manual path remains operational and independent of CI: `rsync` the verified tree to the
host, then run `deploy/run.sh` and `deploy/verify.sh`. It is also the recovery path
when the runner on the host is unavailable.

`AI_STP_PUBLIC_HOST` and `AI_STP_DOCS_HOST` belong in `.env.prod` on the host, not
in the repository. Both are bare host names and carry no scheme: the stack asks no
authority for anything, so they name a server rather than an origin (`ADR-0135`).
Either may hold several space-separated names, as nginx's own `server_name` does;
the first names the rendered file and, unless `AI_STP_TLS_LINEAGE` says otherwise,
the certbot directory.

The agent on the host executes only the contents of the monotonic ref published by the
release job. Its deploy key has read-only access to Contents; there is no Actions
credential on the production host.

## Changing the deployment source

This is needed once and is described here because rollback protection rejects it
correctly, but the rejection looks like a malfunction.

The mirror on the host stores objects from the previous source, so the recorded baseline
resolves, but the two histories have no common ancestor. The script refuses:

```text
deployment ref is not a fast-forward from current=<old> candidate=<new>
```

This is not a defect or a reason to weaken the check: it must hold within a single
history. The transition requires a deliberate baseline reset.

```sh
sudo systemctl stop ai-stp-pull-deploy.timer
# The mirror is a cache. Recreating it from the new source both removes objects that
# the host no longer needs to store and makes the recorded baseline unresolvable, which
# the script handles itself.
rm -rf /var/lib/ai-stp-deployer/repository.git
sudo systemctl start ai-stp-pull-deploy.service
sudo systemctl start ai-stp-pull-deploy.timer
```

Before the transition, verify that the new source is reachable from the host at all—otherwise the timer
will fail once a minute without explanation:

```sh
git ls-remote https://github.com/ai-engineers-guild/ai-stp.git refs/heads/deploy/prod
```

While `deploy/pull-deploy.sh` in the deployed tree still carries the old default
address, the source is set in a unit drop-in; it is removed as soon as the new
default value reaches the host with the release.

```sh
sudo mkdir -p /etc/systemd/system/ai-stp-pull-deploy.service.d
printf '[Service]\nEnvironment=AI_STP_PULL_REPOSITORY=%s\n' \
  https://github.com/ai-engineers-guild/ai-stp.git \
  | sudo tee /etc/systemd/system/ai-stp-pull-deploy.service.d/10-source.conf
sudo systemctl daemon-reload
```

After the transition, `git_commit` in `GET /v1/system/version` must resolve to a
commit in the new source; that is the confirmation, not a log entry.

## Deployment from an exact commit

The preferred path is the script with locking:

```bash
export AI_STP_COMPOSE_FILE=docker-compose.prod.yml
export AI_STP_ENV_FILE=.env.prod
# On a host whose root is not a repository, name the commit being deployed;
# without it the artifact record is written empty and rollback loses its baseline.
export AI_STP_API_GIT_COMMIT="$(sed -n 's/^git_commit=//p' .deploy-state/current)"
./deploy/deploy.sh
```

Manual equivalent (the order is mandatory: migrate → seed → API ready → content-import → web):

```bash
export AI_STP_API_GIT_COMMIT="$(git rev-parse HEAD)"
docker compose -f docker-compose.prod.yml --env-file .env.prod config
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d postgres rustfs
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrate
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm seed
docker compose -f docker-compose.prod.yml --env-file .env.prod rm -fs content-import
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d api worker content-import web docs
```

Before `up`, the production worker Compose configuration requires the
`ai-stp-worker` profile (`userns`) to be loaded into the kernel. `deploy/deploy.sh` invokes
`deploy/load-apparmor.sh` itself. The manual path uses the same script as the user who already communicates with Docker:

```bash
./deploy/load-apparmor.sh
```

Do not set `apparmor=unconfined` or `privileged: true`, and do not change
`kernel.apparmor_restrict_unprivileged_userns`: on Ubuntu 24.04, an unconfined
user namespace still cannot be created. See `safety-scan.md` for details.

### Dev stack (local)

No host proxy is used in dev. The browser origin is the published `web`.

```bash
export AI_STP_API_GIT_COMMIT="$(git rev-parse HEAD)"
docker compose -f docker-compose.dev.yml config
docker compose -f docker-compose.dev.yml up -d --build
# Web UI:  http://localhost:3000
# API:     http://localhost:8000  (also via Next rewrite: http://localhost:3000/v1/...)
```

`AI_STP_API_GIT_COMMIT` is required for the `content-import` image: `.git` is not in the build
context, and the bake rejects a zero placeholder. Web is bind-mounted in dev and
waits for `content-import` with `service_completed_successfully`.

The Compose defaults set `AI_STP_USE_MOCKS=false` (the real API). A purely offline frontend
sets `AI_STP_USE_MOCKS=true` in `.env.dev`. Staging smoke always uses `false`.

## Migration and seeding order

1. `postgres` healthy.
2. `migrate`: `alembic upgrade head` (forward only).
3. `seed`: `python -m ai_stp_platform.seed_cli`—the idempotent first-party
   catalog (`REQ-2110` / `REQ-2405`).
4. `api` / `worker` start after a successful seed.
5. `content-import`—a one-shot after a healthy `api`: GET
   `/v1/content/repository/state`, then POST the embedded snapshot. An empty
   token, an empty hub, and a zero commit cause rejection. The scripts remove the previous
   container (`compose rm -fs content-import`); otherwise, an exited-0 container skips the POST.
6. `web` starts only after `content-import` exits 0. The stack starts no proxy in
   either environment (`ADR-0135`); in **prod** the host's nginx is already running
   and reaches `api`, `web` and `docs` on their loopback ports, so a deploy that
   only changes application code needs no proxy action at all. A change to the
   route split is applied separately with `sudo deploy/nginx/render.sh`.

Application rollback does not touch the schema (`REQ-2410`): `deploy/rollback.sh` restores
the previous exact artifact and leaves the revision in place.

Downgrading the revision is a separate operation (`REQ-2418`, `ADR-0081`):

```bash
./deploy/downgrade.sh --to 0018_repair_catalog_passport_digests --yes
```

The target revision is required, the backup is created in the same run, and the
source and target revisions are recorded in `.deploy-state/last-downgrade`.
`--skip-backup` additionally requires `AI_STP_DOWNGRADE_ACCEPT_DATA_LOSS=1` and is suitable
only for an environment with nothing to lose.

## Health and diagnostics

| Check | URL (prod: through the host's nginx, or directly on `:58082`; dev: `:8000` or same-origin `:3000/v1`) | Expected result |
| -------- | ----------------- | -------- |
| Liveness | `/v1/health/live` | 200 |
| Readiness | `/v1/health/ready` | 200, otherwise 503 |
| Safe diagnostics | `/v1/system/version` | `version`, `environment`, `git_commit`, `schema_revision` without secrets |

```bash
curl -fsS "$ORIGIN/v1/health/live"
curl -fsS "$ORIGIN/v1/health/ready"
curl -fsS "$ORIGIN/v1/system/version"
```

Readiness prevents the service from being declared ready until the database, migrations, and storage
are ready (`SPEC-017`). The deployment script aborts on the readiness timeout and does not
consider the artifact healthy.

The workflow retains the internal check and then starts an external probe from the deployment
runner. `deploy/verify_public.py` accepts only a bare `https` origin, uses
ordinary DNS and the system TLS trust chain, limits responses, and compares
`git_commit`, `environment`, and the single head revision calculated from the migrations.
It has no options to disable TLS or override DNS.

### Routing

**Prod (the host's nginx, from `deploy/nginx/ai-stp.conf.template`):**

- `/v1/`, `/docs`, `/redoc`, `/openapi.json`, `/schemas/provider-protocol/` → the API bind
- everything else → the web bind
- the documentation host → the docs bind
- only nginx is exposed externally; the stack's own ports stay on loopback

**Local dev (no host proxy):**

- host `web:3000`—UI; Next rewrite `/v1/*` (and docs paths) → `api:8000`
- host `api:8000`—direct API (legacy OAuth callback)
- `postgres` and `rustfs` are available only on the internal network
- `web` accesses the API through `AI_STP_API_BASE_URL=http://api:8000` (internal)

## Logs

Structured api/worker JSON logs are stored on the `/var/log/ai_stp` volume, rotated daily,
with 14 files retained (`ADR-0039`). Request correlation is provided by the
`X-Request-Id` / `request_id` middleware. Logs contain no tokens, cookies, object bytes,
private paths, or environment values (`REQ-2408`, `SPEC-013`).

## Backup

```bash
./deploy/backup.sh --label pre-deploy
# Directory: .backups/<timestamp>[-label]/ with MANIFEST.txt
```

- PostgreSQL: logical `pg_dump` (custom format)
- RustFS: copy of the volume data
- Retention: `AI_STP_BACKUP_RETENTION` (the 7 newest directories by default)
- Schedule: example `deploy/schedule-backup.example.cron`
- The backup log does not print secrets or object bytes

## Restoration

```bash
./deploy/restore.sh --from .backups/<name> --yes
```

The script stops writers, restores the dump and objects, removes the
previous `content-import`, and starts the stack. The one-shot resubmits the snapshot
from the current image: repository articles match the image, while staff content comes from the backup.
Rehearse on a restored copy before making a production change.

## Rollback

Rollback = redeploying the **previous exact** Git commit from
`.deploy-state/previous`. A destructive reverse migration is **not** performed.

```bash
./deploy/rollback.sh --yes
```

If the previous code is incompatible with the already applied schema, readiness will
fail—this is an expected abort; then proceed according to
`docs/engineering/schema-evolution.md` and
`docs/operations/runbooks/database-migration.md`.

## Deploy lock

`deploy/deploy.sh` and `deploy/rollback.sh` are serialized via `flock` on
`.deploy-state/deploy.lock`. A repeated deployment is idempotent (Compose up +
migrate/seed no-op). A concurrent deployment exits with a held-lock
error.

Before `rsync` begins, the workflow atomically writes `.deploy-state/in-progress` with the exact
SHA and the `transfer_started` stage. `deploy/deploy.sh` updates the marker after config,
the build stage, dependency preparation, migration, seeding, startup,
and the liveness and readiness checks. After successful
readiness, it moves the previous `current` to `previous`, atomically writes the new
`current`, and removes the marker. After an interruption, the next run reports the previous SHA
and stage and repeats the idempotent forward path. `.deploy-state`, `.backups`, and host-only
environment files are excluded from `rsync --delete`.

### Unresolvable baseline in `current`

Symptom: `ai-stp-pull-deploy.service` fails on every timer tick with
`fatal: Not a valid object name unknown^{commit}` and exit code 128, while the deployed
environment continues to run the previous release.

Cause: `.deploy-state/current` contains `git_commit=unknown`. Under the pull model,
the deployment root is extracted via `git archive` and contains no `.git`,
so `rev-parse` returned `unknown`; that value entered the record, and
the next run read it as the baseline and asked Git to resolve it. The record could not
then be replaced because the script aborted earlier.

Both sides are covered—`current_git_commit` takes `AI_STP_DEPLOY_COMMIT`, and
an unresolvable baseline is no longer written and yields
`pull_deploy_baseline_unresolvable` when read. To recover an already corrupted record,
replace the `git_commit=` line in `.deploy-state/current` with the commit the environment
is actually running (`GET /v1/system/version`), preserving a copy of the file. An empty
value is also valid and means there is no baseline, but rollback protection
will not work at this step in that case.

### `203/EXEC` for `ai-stp-pull-deploy.service`

Symptom: the timer fires every minute, the unit fails with `status=203/EXEC`,
`/v1/system/version` does not advance, and `deploy/prod` is already at a newer SHA.

Cause: `pull-deploy.sh` sets `umask 077` and used to extract `git archive` via
`tar -x` without `--preserve-permissions`. Files from the archive with mode `0755`
ended up as `0600` on disk. systemd does not run `ExecStart=` without the owner's
execute bit. The deployed tree continues to operate meanwhile:
the script does not start, so it updates nothing.

To recover an already corrupted tree: `chmod u+x /home/ubuntu/ai_stp/deploy/*.sh`,
then `systemctl start ai-stp-pull-deploy.service`. The script now extracts
with `--preserve-permissions` and reapplies the execute bit to scripts invoked by name
after `rsync`.

## Smoke test on the deployed slice

Verify through the public origin the host's nginx serves, not the direct loopback
binds: what the binds prove is that a container answers, and what the public origin
proves is that the name, its certificate and the route split reach it.

1. Landing page: `GET /` (or `/ru`, `/en`)—200, shell renders.
2. Catalog: `GET /ru/catalog` (or en)—list/empty state without 5xx.
3. OAuth: real flow `#80` when available; otherwise, a web mock session
   (`AI_STP_USE_MOCKS=true`) with the gap explicitly recorded in the evidence.
4. Devices: list and revoke on the authenticated path after sign-in.

```bash
# Examples (substitute ORIGIN)
curl -fsS -o /dev/null -w '%{http_code}\n' "$ORIGIN/"
curl -fsS -o /dev/null -w '%{http_code}\n' "$ORIGIN/ru/catalog"
curl -fsS -o /dev/null -w '%{http_code}\n' "$ORIGIN/v1/health/ready"
```

## Web images

| File | Purpose |
| ---- | ---------- |
| `apps/web/Dockerfile.dev` | bun + `bun run dev`, EXPOSE 3000 |
| `apps/web/Dockerfile.prod` | multi-stage standalone → `node:22.18.0-slim`, non-root uid 10001 |

```bash
docker build -f apps/web/Dockerfile.dev -t ai-stp-web:dev apps/web
docker build -f apps/web/Dockerfile.prod --build-arg AI_STP_WEB_PROFILE=public_saas -t ai-stp-web:prod .
```

## Required evidence checklist (#84 / REQ-2412)

Complete when closing the issue on a real checkout/host:

| Evidence | Command / artifact | Result |
| -------------- | ------------------ | --------- |
| Commit / artifact | `git rev-parse HEAD`, image ids | |
| Compose validation | `docker compose -f … config` | exit |
| Web dev/prod build | `docker build -f apps/web/Dockerfile.*` | exit |
| Migrate / seed | output of one-shot services | exit |
| Liveness / readiness | curl exit codes + body status | |
| Safe diagnostics | `/v1/system/version` without secrets | |
| Routing / isolation | api vs web path; pg/rustfs are not public | |
| Backup + restore rehearsal | `deploy/backup.sh`, `deploy/restore.sh --yes` | |
| Rollback rehearsal | `deploy/rollback.sh --yes` | |
| Deploy lock / idempotent repeat | second deployment while locked; repeated deployment | |
| Smoke | landing, catalog, OAuth, devices | |
| Gates | `just docs-check`; `just web-static` and `just web-build` | |
| Tests not run | list them | |
| Residual risks | list them | |

## Manually recreating a single service

`AI_STP_API_GIT_COMMIT` comes not from `.env.prod`, but from the environment of whoever
runs Compose: `pull-deploy.sh` and `deploy.sh` export it. Therefore,
`docker compose up -d --no-deps api`, entered manually, will start a container with
an empty value, and `GET /v1/system/version` will begin returning an empty
`git_commit`. Production remains healthy, and nothing issues a warning: the discrepancy
is visible only to someone who inspects the response, while `just evidence-live` for the exact SHA
then fails.

The correct form is to take the commit from where the deployment recorded it:

```bash
cd /home/ubuntu/ai_stp
COMMIT=$(sed -n 's/^git_commit=//p' .deploy-state/current)
AI_STP_API_GIT_COMMIT="$COMMIT" \
  docker compose -f docker-compose.prod.yml up -d --no-deps api
docker exec ai_stp-api-1 env | grep GIT_COMMIT
curl -s https://<host>/v1/system/version
```

The response must be checked: an empty `git_commit` is what this step fixes
and also what it creates if the variable is forgotten.

## Residual risks (typical)

- Until real OAuth `#80` is available, the sign-in smoke test uses the mock-session path;
  the gap is recorded, not hidden.
- `AI_STP_PUBLIC_HOST` and ACME require DNS and ports 80/443 on the deployment host.
- Rollback without a down migration does not revert data already written under the new schema.
- The `deploy/*.sh` scripts are designed for a Linux host (flock); on Windows, use
  Docker Desktop + Git Bash/WSL or a remote deployment host.
