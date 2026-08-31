---
description: "Target infrastructure for the MVP server mode."
last_verified: "2026-08-05"
---

# Infrastructure

## Components

```text
reverse proxy
├── Next.js
└── FastAPI
    ├── PostgreSQL
    ├── worker
    ├── RustFS/S3
    ├── Google/GitHub OAuth
    └── Resend
```

## Hosting

The MVP server environment is hosted on the owner's own `server-nddev-kazakhstan` server; no separate cloud budget is allocated. The reverse proxy, application, database, worker, and object storage run on that node within its resources. The public domain is fixed before server mode is opened; until then, examples use a placeholder catalog address.

The node is shared with the owner's other services, and this constraint determines
port publication. External ports `80` and `443` belong to the host proxy, which
already serves neighboring domains and terminates TLS. Caddy therefore remains the
stack entry point but is published on a local port: the addresses are set by
`AI_STP_CADDY_HTTP_BIND` and `AI_STP_CADDY_HTTPS_BIND`, whose defaults (`80` and
`443`) leave an unshared installation unchanged. Only the publication point moves,
not Caddy's role. When the host proxy already holds the certificate, an
`AI_STP_PUBLIC_HOST` using the `http://` scheme prevents Caddy from requesting ACME
for a name whose challenge it cannot answer on port `80`.

## Rules

- one modular monolith, not a set of microservices;
- API and worker may be separate processes of one release artifact;
- PostgreSQL is the source of truth for metadata;
- RustFS stores immutable artifact bytes;
- object storage is not directly accessible without authorization;
- processes run without root;
- health and readiness are separate;
- migrations run as a separate release step;
- PostgreSQL and object-storage backups are verified through restoration;
- production deployment is outside the coding agent's automatic authority.

Specific images, resources, and environments are fixed after executable code and measurements exist.

Deployment topology, reverse proxy, and networking belong to `ADR-0040` and `SPEC-019`; the job queue mechanism belongs to `ADR-0038` and `SPEC-018`; and the execution and observability layer belongs to `SPEC-017` and `ADR-0039`. Those decisions are not repeated here.
