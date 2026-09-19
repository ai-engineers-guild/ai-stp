# Docker — the container and deployment standard

Docker is the runtime substrate for the platform: every serving process runs
in a container built from this repository. The deployment model is **pull**:
a green `check` on `main` lets `.github/workflows/deploy.yml` advance one
monotonic ref (`deploy/prod`); the host's systemd timer runs
`deploy/pull-deploy.sh`, which fetches the ref anonymously, unpacks it with
`git archive`, rsyncs it over the deployment root, and runs
`deploy/run.sh` → `deploy/deploy.sh`, which builds the images **on the
server, from the deployed commit** and brings the stack up under a lock.
There is no registry and no prebuilt artifact: the commit is the artifact,
and `AI_STP_API_GIT_COMMIT` carries its identity into the running services.

Everything below exists to keep that chain reproducible, locked and
rollback-safe.

## Version contract

- Base images and `uv` are pinned **by digest, named by tag**
  (`python:3.12-slim@sha256:…`). The tag documents intent; the digest proves
  which build ran. Enforced by
  `tests/contract/test_container_bases_are_pinned.py`.
- One image+tag resolves to **one digest across the tree**. Two Dockerfiles
  pinning different republishes of `python:3.12-slim` once meant the platform
  image and the scanner image ran different interpreters with nothing saying
  so.
- Debian packages install only through the canonical pattern: a dated
  `snapshot.debian.org` mirror + exact `pkg=version` + `rm -rf
  /var/lib/apt/lists/*`, in one `RUN`. `apt-get install pkg` against the
  moving index is rejected — two builds of one commit would resolve
  different packages.
- Compose files declare no `version:` key (obsolete in Compose v2+). Compose
  v2 (`docker compose`, the plugin) is the only supported CLI; the
  `docker-compose` hyphenated binary is not used anywhere.
- The `uv` copied into images is the version every gate installs
  (`install-uv.sh`), held together by
  `test_deploy_contract.py::test_the_images_resolve_the_lockfile_with_the_uv_every_gate_installs`.

## Rules

1. **Every `FROM` and every production `image:` is digest-pinned.**
   `Dockerfile*` at the root *and* `apps/web/Dockerfile*` are both covered
   by the contract test — the web image lives under `apps/` but answers the
   same rule. A republished tag leaves no trace; the 2026-08-20 `rustfs`
   `:latest` republish took production down for real (`#394`).
2. **Dev is exempt from digest pinning only where the exemption is the
   point.** `docker-compose.dev.yml` pulls `postgres:16` by tag because a
   dev stack tracks its major — that is the one named exemption, recorded in
   the test. `rustfs` in dev pins the *same* digest as prod: a dev stack
   resolving a different build cannot reproduce what production hit.
   `apps/web/Dockerfile.dev` pins the same bun digest as `Dockerfile.prod`
   for the same reason.
3. **`${VAR:-default}` image references pin their default by digest.** The
   variable is the operator's override; the default is this tree's answer
   for an unconfigured checkout. Enforced by
   `test_compose_image_defaults_are_pinned_by_digest`.
4. **No `:latest`, no untagged `image:` anywhere** — including overlay
   files. Enforced by `test_no_compose_file_resolves_an_image_by_a_moving_tag`.
5. **Final stages run as `appuser` (uid 10001), never root.** `USER root`
   is allowed in *intermediate* stages only, and each such site carries an
   inline `# hadolint ignore=DL3002` with the reason in the comment lines
   above it — hadolint honors the directive only as the last comment line
   before the instruction.
6. **Apt installs follow the snapshot pattern** (Version contract). Alpine
   (`apk`) has no version-retention equivalent: a dev-only image may take
   the index's package unpinned, documented with `# hadolint
   ignore=DL3018`. Production-path images may not.
7. **Build contexts are minimal and secret-free.** `.dockerignore` excludes
   `.env*` (only `*.example` re-included), `.git`, `deploy` (except the two
   nginx files `Dockerfile.user-docs` copies), tests and build output. A
   `<dockerfile-name>.dockerignore` beside a Dockerfile *replaces* the root
   ignore for that build — `apps/web/Dockerfile.prod.dockerignore` is what
   lets the web image see `apps/web/` while the platform images cannot.
   Adding a Dockerfile means deciding which ignore file governs it.
8. **Secrets never enter images or build args.** `ARG`/`ENV` hold
   build-time placeholders only (`AI_STP_SESSION_SECRET` is a literal
   placeholder by design); real secrets arrive via `env_file` at runtime.
   `deploy.sh` checks required env values with `require_env_value` —
   greps, never `source`s — *before* any build or container recreation, so
   a missing secret leaves the healthy release serving.
9. **Compose is the unit of validation.** `docker compose config -q` must
   pass for `docker-compose.prod.yml`, `docker-compose.dev.yml`, and every
   overlay combination the runbooks use (dev+corporate, dev+seo-enrichment
   `--profile seo_enrichment`). The overlays are invalid alone by design —
   they patch dev services. `deploy.sh` runs `compose config` before
   mutating anything.
10. **Every long-running service reports health.** `restart: always`
    services carry a `healthcheck`; one-shot jobs (`restart: "no"`) prove
    themselves by exit code. Probes use tools already in the image
    (`pg_isready`, `python`, `node`, busybox `wget`) — no extra packages
    for checking alone. Enforced by
    `test_every_long_running_prod_service_reports_health`.
11. **Ordering is stated, not assumed.** `depends_on` carries
    `service_healthy` / `service_completed_successfully` conditions; the
    one-shot chain is migrate → storage-migrate → seed → api/worker +
    content-import → web. `deploy.sh` stages that order explicitly and
    records each stage in `.deploy-state/in-progress` so an interrupted
    deploy restarts the forward path.
12. **Prod binds loopback only.** Published ports default to
    `127.0.0.1:*`; the host's nginx owns TLS and routing (ADR-0135).
    `internal: true` networks carry no outbound route; data services
    (postgres, rustfs) live there and publish nothing.
13. **No privilege that is not named and justified.** `security_opt`,
    `privileged`, `user: root`, `network_mode: host`, writable bind mounts
    of host paths into prod services are rejected. The worker's
    `seccomp=unconfined` + `apparmor=ai-stp-worker` is the one accepted
    exception: bwrap needs a user namespace Docker's default seccomp
    denies, and the named profile is installed by
    `deploy/load-apparmor.sh` before the container starts.
14. **Build is server-side, from the commit.** No registry, no
    `docker push` anywhere in the chain. `infra-build` reproduces the
    server build locally for review; `compose build` needs no
    `.env.prod` (`env_file` is `required: false`, args carry defaults).
15. **Deploy identity travels with the bytes.** The root has no `.git`
    after `git archive` + rsync, so `AI_STP_DEPLOY_COMMIT` /
    `AI_STP_API_GIT_COMMIT` name the commit; `write_artifact_record`
    refuses to record `unknown`. Rollback (`deploy/rollback.sh --yes`)
    redeploys the recorded previous commit and never runs a schema
    down-migration — `deploy/downgrade.sh` is the separate, backup-first
    path for that.
16. **The pull model stays anonymous and monotonic.** `pull-deploy.sh`
    fetches over HTTPS with no credential helper, refuses non-fast-forward
    (anti-rollback), locks with `flock`, and prunes extracted releases to
    current+previous. Enforced by `test_deploy_contract.py`.

## Accepted and rejected features

| Feature | Verdict | Reason |
| --- | --- | --- |
| Digest pinning (`@sha256:`) | **required** on every `FROM` and prod `image:` | a republished tag is invisible; `#394` |
| `snapshot.debian.org` + exact apt versions | **required** for Debian packages | the only reproducible apt install |
| Multi-stage builds | **required** | toolchains (`bun`, `golang`, `uv`) never reach runtime stages |
| `uv sync --locked --no-dev --no-cache` | **required** for Python deps | the lockfile is the contract; `--no-cache` keeps layers clean |
| `COPY --chown=` / `--from=` | **required** for copied trees | no recursive `chown -R` on multi-hundred-MB trees (was a hung build step) |
| `env_file` with `required: false` | **accepted** | lets `compose config`/`build` work without secrets; `deploy.sh` checks required keys itself |
| `x-` extension anchors (`x-app-env`) | **accepted** in dev compose | one env block across services |
| Compose `profiles` | **accepted** for opt-in stacks | `seo_enrichment` services start only when asked |
| `!override` on volume lists | **accepted** for overlays | corporate-local replaces dev mounts deliberately |
| `depends_on` with conditions | **required** | `service_healthy` / `service_completed_successfully`, never bare |
| Named volumes for data | **required** | `pgdata`, `rustfs`, `osv_offline`, `clamav_db`, `logs` |
| Bind mounts into prod services | **restricted** — read-only, repo-relative, non-secret | `./docs-user-facing/content:/content:ro`, `./deploy/geoip:/srv/geoip:ro` are the accepted set |
| `secrets:` / `configs:` top-levels | **allowed, unused** | env_file covers the need today; adopt when a secret must be a file |
| `ports` beyond loopback in prod | **reject** | the host nginx owns the public edge (ADR-0135) |
| `network_mode: host` | **reject** | bypasses the internal/edge split and the loopback binding |
| `privileged: true` | **reject** | the worker's exception is named and narrower (rule 13) |
| `restart: always` without `healthcheck` | **reject** | a wedged process reports `running`; rule 10 |
| `docker run` ad-hoc operations | **reject** | every container enters through compose so ordering/health/locking apply |
| `docker push` / registry pulls of own images | **reject** today | the artifact is the commit, built on the host; revisit only with a registry decision |
| `SBOM`/provenance attestations | **deferred** | meaningful once images leave the host; currently nothing consumes them |
| Build cache mounts (`RUN --mount=type=cache`) | **allowed** for package caches | `uv --no-cache` already keeps them out; add where a build measures slow |
| `docker buildx bake` | **allowed, unused** | compose already names every build; a bake file would be a second index |
| Compose `watch`/`develop` | **reject** | dev uses explicit bind mounts + named volumes for the HMR graph |

## Verification

| Check | Where it runs | What it proves |
| --- | --- | --- |
| `just infra-static` | local, on demand (outside `check`) | hadolint clean at `warning` threshold (`.hadolint.yaml`), shellcheck clean on `deploy/*.sh`, all four compose contexts render |
| `just infra-build` | local, on demand | the prod images build from this checkout exactly as the host builds them |
| `just infra-up` / `infra-down` | local dev | the dev stack lifecycle |
| `test_container_bases_are_pinned.py` | `back-test`, CI | every `FROM` digest-pinned, prod `image:` digested, one tag → one digest, `${VAR:-}` defaults digested |
| `test_compose_safety_deploy.py` | same | worker/safety wiring, content-import ordering, no moving tags, healthcheck coverage |
| `test_deploy_contract.py` | same | promote-workflow guarantees, pull-deploy monotonicity, preflight ordering, verify.sh semantics |
| `docker compose config` | inside `deploy.sh` before any mutation | the file the host runs is the file that rendered |
| `deploy/verify.sh` + `verify-public` job | host + CI | liveness/readiness on the published origin, worker image currency |

## Changing the infra surface — checklist

1. New `FROM`/`image:` → digest-pin it; run
   `tests/contract/test_container_bases_are_pinned.py`.
2. New apt package → snapshot + `=version` + lists cleanup in one `RUN`.
3. New long-running compose service → healthcheck + restart policy +
   network choice (`internal` unless it must answer from outside).
4. New compose file → add its valid combinations to `infra-static`.
5. New Dockerfile → decide which `.dockerignore` governs it (root vs
   `<name>.dockerignore`), then run `just infra-static`.
6. Touching `deploy/*.sh` → `just infra-static` (shellcheck) and re-run the
   deploy-contract tests.
7. A deliberate hadolint warning → `# hadolint ignore=<RULE>` as the last
   comment line above the instruction, reason in the lines above it.
8. Nothing here grants an exception silently: each rejected feature in the
   table names its reason — a new exception is a new row, not a quiet diff.
