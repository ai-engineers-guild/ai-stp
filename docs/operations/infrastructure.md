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
port publication. External ports `80` and `443` belong to the host's `nginx`, which
already serves neighboring domains and terminates TLS with certbot certificates.
The stack therefore ships no proxy of its own (`ADR-0135`): `api`, `web` and `docs`
publish to loopback — `AI_STP_API_BIND`, `AI_STP_WEB_BIND` and `AI_STP_DOCS_BIND`,
defaulting to `127.0.0.1:58082`, `58081` and `58083` — and nginx routes the public
names to them.

The route split is not host-only knowledge: this repository owns it as
`deploy/nginx/ai-stp.conf.template` and `deploy/nginx/ai-stp-docs.conf.template`,
and `deploy/nginx/render.sh` installs one site from them. That script is not part
of the automatic deployment. The pull-deploy unit runs unprivileged with
`NoNewPrivileges=true` and `ProtectSystem=strict` and cannot write `/etc/nginx`;
granting it that would hand the unattended path root over the host's web server.
Applying a routing change is therefore an operator step, run with `sudo`.

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
