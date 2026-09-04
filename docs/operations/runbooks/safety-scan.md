---
description: "Runbook: platform safety scan for publication validation."
last_verified: "2026-09-03"
---

# Runbook: platform safety scan

The server-side security check set runs during publication `validate`
(issues #268 / #270 / #281). Evidence source: `platform_safety_scan`.
Policy version: `safety-3`.

## Worker image and external CLIs

In dev and prod compose, the publication worker is built from
`Dockerfile.worker-safety` (target `worker-safety`) with:

- `AI_STP_SAFETY_EXTERNAL_CLI=1`
- `AI_STP_SAFETY_CACHE_TTL_SECONDS` (default 900) and
  `AI_STP_SAFETY_ASSESSMENT_GENERATION` (bump when assessment inputs change)
- volume `osv_offline` → `/var/lib/ai_stp/osv`
- `AI_STP_OSV_OFFLINE_DIR` and `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY` (one path;
  osv-scanner reads offline packs from the second variable)
- `AI_STP_OSV_MAX_AGE_HOURS`

The API and migrate/seed services remain on the `worker`/`api` targets without
scanner binaries.

## What the skill engine receives

`skill-scanner` loads a **skill package**—a directory containing `SKILL.md`—not the
artifact root. The `ai-stp-component-tree/1` artifact unpacks into `component.json`
and `files/`, so its root is not a package: `skill-scanner` returns
`Error loading skill: SKILL.md not found`, exits with code 1, and prints no report.

The gate passed that root and interpreted the failure as a finding that the scanner
had reported risks. On the corpus, this rejected 96 of 103 components for content
that nobody had read and blocked every setup pinning them. Each engine now receives
one directory for each discovered `SKILL.md`; `skill_packages` in `detail` reports
how many there were. Zero means there was nothing to load—for example, for an
`agent` component—and the engines are not started at all.

Separately, `skill-scanner` requires `name` and `description` in frontmatter. A
`SKILL.md` without them does not load; that is also `degraded` with a reason, not a
finding.

## Per-check time limit

The time allocated to a particular check is set by its `timeout_seconds` in
`safety/policy.py`. `safety/adapters/_cli.py` keeps a `MAX_TIMEOUT_SECONDS` ceiling
as protection against an invalid argument, not as a second policy; a test forbids
declaring more than the ceiling. The whole set also has its own budget in
`safety/orchestrator.py`.

Previously the ceiling was silently 25 seconds while checks declared 30 and 60.
Because nobody reported the difference, increasing the limit changed nothing, and
a scanner killed by the timeout was recorded as a finding: an object was rejected
for dangerous content nobody had seen. A check that does not finish is now
`degraded` and names the reason.

Manual build:

```text
docker build -f Dockerfile.worker-safety --target worker-safety -t ai-stp-worker-safety .
```

Version pins are in `scripts/safety/versions.env`; installation is in
`scripts/safety/install_scanners.sh`. The image includes:

| Tool | Role |
|------|------|
| gitleaks | secrets (secondary to the in-process heuristic) |
| opengrep | SAST with vendored rules in `safety/policy_pack/opengrep/` |
| shellcheck | shell scripts |
| bandit | Python SAST |
| pip-audit | Python SCA |
| gosec | Go SAST |
| govulncheck | Go SCA (required in the image) |
| cargo audit | Rust SCA (when cargo is available on the host) |
| eslint | JS/TS SAST (when available) |
| npm audit | JS SCA |
| cargo deny | Rust policy (strict) |
| osv-scanner | SCA (`--offline` when `AI_STP_OSV_OFFLINE_DIR` is set) |
| PDF in-process | `document_pdf` checks for /JavaScript, /Launch, and similar content |
| clamscan | malware (strict profile) |
| yara | malware IOC pack (strict; in-process marker always) |
| skill-scanner | skill static + `--use-behavioral` data flow (Cisco `cisco-ai-skill-scanner`, required together with independent platform rules) |
| bwrap | Linux network namespace for child external CLIs |

Without `AI_STP_SAFETY_EXTERNAL_CLI`, in-process adapters still run (denylist,
secrets heuristic, MCP/hook static checks, PI/stego, owned skill patterns, and the
malware test marker), as well as offline `network_intent` and bounded decoding of
obfuscation (no more than two layers, 32 candidates, and 64 KiB per candidate).

## Isolation (sandbox)

- Variable: `AI_STP_SAFETY_SANDBOX=auto|off` (default `auto`).
- On Linux with working `bwrap` (unprivileged user namespaces), CLI argv is wrapped
  with `--unshare-net` and an RW bind of the scan workdir.
- If `bwrap` is missing or cannot create namespaces (often the Docker Desktop
  default), the mode falls back to env-only deny:
  `AI_STP_SAFETY_NETWORK=deny`, with proxy variables cleared. Probe details are in
  `doctor_tools()` / `sandbox_status()`.
- The container network policy remains the primary egress control; `bwrap` is an
  additional protection layer.
- Forcibly enabling namespaces on Docker Desktop requires kernel user namespaces
  and a non-default security profile; production Linux workers usually run with
  `auto`.

## Updating offline databases

Offline OSV database (compose volume `osv_offline`):

```text
export AI_STP_OSV_OFFLINE_DIR=/var/lib/ai_stp/osv
export OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/var/lib/ai_stp/osv
/opt/ai_stp/scripts/safety/refresh_osv_db.sh
```

- The script sets `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$DEST` so packs land on the
  volume (`{dir}/osv-scanner/{ecosystem}/all.zip`).
- Production compose downloads only the ecosystems supported by the safety policy
  by default: `PyPI,npm,Go,crates.io`. Expansion requires
  `AI_STP_OSV_ECOSYSTEMS` and support for the new package manifest.
- It does not write `.ai_stp_osv_refreshed_at` when no ZIP packs appeared, avoiding
  false freshness.
- Use a daily host cron or a job that writes to the shared volume.
- Doctor reasons: `not_configured`, `directory_missing`, `no_files`, `no_stamp`,
  `stale`, `ok`.
- SCA adapter: no packs → `not_run` / `offline_db_missing` (not `tool_missing`).
- Age: `AI_STP_OSV_MAX_AGE_HOURS` (default 36). Optional hard gate:
  `AI_STP_OSV_REQUIRE_FRESH=1` (API readiness remains optional; for worker-only
  probes).
- A separate `clamav-refresh` updates ClamAV signatures in shared read-only worker
  volume; the worker starts only after a non-empty `.cvd`/`.cld` appears.

## Storage authentication

- `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` must match
  `AI_STP_STORAGE_ACCESS_KEY_ID` / `AI_STP_STORAGE_SECRET_ACCESS_KEY` on the first
  RustFS volume startup.
- Compose healthcheck: `curl -sf http://127.0.0.1:9000/minio/health/live`.
- API and worker: `depends_on: rustfs (service_healthy)`.

## Honest checks summary

`build_checks_summary` statuses:

| status | meaning |
|--------|---------|
| `pending` | a mandatory check is still `not_run` / `degraded` / `running` |
| `incomplete` | optional engines are planned but missing (`not_run`); percent uses finished verdicts only |
| `available` | coverage is complete; percent is 0–100 over passed/failed/warning |
| `empty` | no bindings |

Fields: `coverage_complete`, `not_run`, `checks_passed_percent` (the share of
`passed` among `passed` + `failed` + `warning`). Optional unfinished checks stay
in the stored snapshot and on `GET …/versions/{version}/checks`; the catalog
card omits them. After a scanner-logic change without a policy bump, delete the
matching `safety_scan_run` row (or restart the worker and wait for a new digest)
so the in-process and persisted caches do not reuse a stale verdict.

## Setup pins

Setup checking reads each pin's `checks_summary` from `components[]` in
`catalog_metadata` and runs `setup_pin_aggregate` without rescanning the merged
tree. A missing or failed mandatory pin fails the setup gate.

## Diagnostics and metrics

```text
python -c "from ai_stp_platform.safety import doctor_tools, safety_diagnostics; import json; print(json.dumps(safety_diagnostics(), indent=2, default=str))"
```

Process counters (structlog plus snapshot, with no Prometheus dependency):

- `safety_scan_total`, `safety_scan_cache_hit_total`
- `safety_scan_duration_ms_*` including buckets and p50/p95/p99
- `safety_check_total`, `safety_check_result_total`, `safety_check_result_by_id_total`
- `safety_check_duration_ms_*` by `check_id`
- `safety_finding_total` by `family:severity`
- `safety_cli_timeout_total`, `safety_cli_missing_total`
- `safety_sandbox_mode_total`
- `safety_queue_claim_*`, `safety_queue_wait_ms_*`, `safety_queue_job_*`,
  `safety_queue_requeued_total`

For reproducible offline performance evidence:

```text
just safety-benchmark --iterations 3 --concurrency 1
```

The command forces `AI_STP_SAFETY_EXTERNAL_CLI=0` and
`AI_STP_SAFETY_SANDBOX=off`, accesses no network, uses fixed ZIP bytes, and prints
JSON. Compare `wall_ms` only across identical environments; required invariants
remain schema, case order, digest, profile, disabled network/CLI, and no mandatory
failures.

Adversarial corpus and JSON report:

```text
just safety-corpus --output .work/safety-corpus-report.json
```

The command materializes each component fixture ZIP in sequence, runs the same
`run_safety_suite` used by publication validation, and separately checks the setup
through `setup_pin_aggregate`. Success requires an exact match of expected
`check_id`/`rule_id` values and no findings on clean controls. Raw fixture bytes do
not enter the report.

Corpus v2 contains 156 file scenarios: 134 malicious and 22 clean. It includes
MCPTox classes for metadata preconditions and argument substitution, MCP tool/schema
modification, tool shadowing, resource/prompt/output poisoning, dangerous chains,
subagent and memory attacks, persistence, supply chain, limited multilayer
encoding, Unicode Tag Block, homoglyphs, and structural hiding in Markdown.
Controls pin stable MCP snapshots, bounded delegation, and defensive text that
describes the prohibited attack.

API readiness (`/v1/health/ready`) depends only on database/migrations/storage, so
missing scanners do not bring down the public API. Worker operations use
`doctor_tools`.

## Scenario matrix (in-process)

Unit scenarios in `tests/unit/platform/test_safety_scenario_matrix.py`:

| Fixture | Expected gate signal |
|---------|----------------------|
| clean skill | no mandatory `failed` |
| secret skill (`ghp_…`) | secrets family fails |
| toxic skill (pipe shell / PI) | skill gate fails |
| clean MCP | the `mcp_config` path does not cause a mandatory failure |

External CLIs are not required for this matrix.

## Common failures

| Symptom | Action |
|---------|--------|
| All publishes are blocked with `not_run` | No artifact bytes reached validate; check the object-store fetch |
| External CLI hangs | `AI_STP_SAFETY_EXTERNAL_CLI` belongs only in worker-safety; the check declares the limit and the runner ceiling is `MAX_TIMEOUT_SECONDS` |
| Check is `degraded` and `reason` says `did not finish within Ns` | The scanner timed out; inspect worker load and that check's declared `timeout_seconds`, not the object's contents |
| Host AV blocks temporary files | Do not place a full EICAR; use marker `AI_STP_MALWARE_TEST_MARKER_V1` |
| OSV is stale | Run `refresh_osv_db.sh`; compare the stamp with `AI_STP_OSV_MAX_AGE_HOURS` |
| Sandbox is always `env_only`, worker `unhealthy` | See the section below. `bwrap` is already in the image; do not install it again. |

### Worker `unhealthy`: `bwrap` probe returns `env_only`

`safety_readiness()` requires `detect_sandbox_mode() == "bwrap"`. On Ubuntu 24.04,
the host keeps `kernel.apparmor_restrict_unprivileged_userns=1`. `seccomp=unconfined`
in compose is insufficient: the `docker-default` profile blocks both mount and the
user namespace. Removing AppArmor from the container (`apparmor=unconfined`)
changes the error to `loopback: Failed RTM_NEWADDR`—unconfined has no `userns` rule,
so the namespace still cannot be created.

The repository does not remove the sysctl or run the worker as root. Instead, prod
compose sets `apparmor=ai-stp-worker`, and `deploy/load-apparmor.sh` loads a profile
with a `userns` rule into the kernel before `compose up` starts the worker. The
`pull-deploy` unit keeps `NoNewPrivileges=true`, so loading runs through the Docker
daemon (which is already root) and `nsenter` enters PID 1's mount namespace; a copy
of the profile in `/etc/apparmor.d/` survives reboot. The container remains uid
`10001`.

Until the profile is loaded, the worker healthcheck is red and every external CLI
with `AI_STP_SAFETY_REQUIRE_BWRAP=1` exits with code 126. `deploy/verify.sh` refuses
to proceed when the healthcheck is `unhealthy`.
