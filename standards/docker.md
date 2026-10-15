# Containers

Compose files, Dockerfiles and deployment scripts live in [deploy](../deploy).
The [deployment runbook](../docs/operations/runbooks/deploy.md) covers promotion,
settlement and recovery. Production builds from its qualified source commit.

Base images and production image defaults are digest-pinned. Dockerfiles own
package versions and Debian snapshot dates. Development PostgreSQL tracks its
major tag; production remains digest-pinned. Final application stages run as a
non-root user. Build contexts exclude credentials, local state and build output.

Compose owns service ordering, health checks, networks and persistent volumes.
Production ports bind loopback behind the host proxy. Runtime secrets come from
the authorized host environment and only reach the services that consume them.
Never print them or place them in image layers. Deployment validates its
configuration before mutation. Preserve named data volumes during cache cleanup.

For changes, run `just infra-static` and the affected contract tests:
`test_container_bases_are_pinned.py`, `test_compose_safety_deploy.py` and
`test_deploy_contract.py`. `just infra-build` checks actual image construction.
Use the compose files and tests for exact exceptions and supported combinations.
