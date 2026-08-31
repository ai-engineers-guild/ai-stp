---
description: "Decision to drop the in-stack Caddy container and let the deployment host's nginx be the only edge proxy, with the route split owned by a template in this repository."
last_verified: "2026-08-31"
---

# ADR-0135: nginx on the host is the only edge proxy

Status: accepted. Supersedes the proxy-routing part of `ADR-0044` and the
`Caddy` choice `ADR-0040` made; the backup, rollback and deployment-locking
mechanisms in `ADR-0044` are untouched.

## Context

`ADR-0040` chose `Caddy` as the reverse proxy and the only public endpoint, and
`ADR-0044` gave it the route split between `api` and `web`. Both decisions
assumed the stack owned ports 80 and 443.

The deployment host has not matched that assumption for some time. It serves
several unrelated sites, so nginx already listens on 80 and 443, already
terminates TLS with certbot-issued certificates, and already proxies the public
names to the stack. `Caddy` was pushed behind it onto `127.0.0.1:58080` and its
automatic HTTPS was switched off by giving both site addresses an explicit
`http://` scheme — the configuration comments in `.env.prod.example` recorded
this as a workaround for certificate orders that could not succeed.

What remained was a proxy that proxied to a proxy. The second hop added a
container, two volumes, a bind-mounted configuration file whose inode had to be
force-recreated on every deploy, and a second place where a routing rule could
be written. It terminated no TLS, obtained no certificate and made no routing
decision the host's nginx could not make.

The `Caddy` image was also serving a second, unrelated purpose: the static file
server inside the user-documentation image.

## Decision

The stack ships no proxy. `api`, `web` and `docs` publish to loopback
(`AI_STP_API_BIND`, `AI_STP_WEB_BIND`, `AI_STP_DOCS_BIND`, defaulting to
`127.0.0.1:58082`, `58081` and `58083`), and the deployment host's nginx is the
only public entry point.

The route split stays a fact this repository owns, as
`deploy/nginx/ai-stp.conf.template` and `deploy/nginx/ai-stp-docs.conf.template`.
It is unchanged: `/v1/`, `/docs`, `/redoc`, `/openapi.json` and
`/schemas/provider-protocol/` reach `api`, everything else reaches `web`, and the
documentation host reaches `docs`.

`deploy/nginx/render.sh` installs a template for one host name and reloads nginx.
It is not part of `deploy.sh` and not part of the automatic deployment. The
pull-deploy unit runs as an unprivileged user with `NoNewPrivileges=true` and
`ProtectSystem=strict` and cannot write `/etc/nginx`; giving it that power would
hand the unattended path root over the host's web server in exchange for a step
that runs when a routing rule changes, which is rarely. Applying a rendered
template is therefore an operator step run with sudo.

Certificates are certbot's, on the host, with its existing renewal timer. The
lineage is a separate input from the host name because certbot names a directory
after the first request for a name: a reissue lands in `example.com-0001` while
the site is still `example.com`.

The documentation image serves its built site with `nginx:1.27-alpine` and
`deploy/nginx/user-docs.conf`. This is not the edge; it is a static file server
that happens to now be the same program.

## Consequences

`AI_STP_PUBLIC_HOST` and `AI_STP_DOCS_HOST` become host names rather than
origins, and carry no scheme: nothing in the stack asks a CA for anything, so
the scheme no longer switches a behaviour on. `AI_STP_CADDY_HTTP_BIND` and
`AI_STP_CADDY_HTTPS_BIND` are gone.

`deploy/verify.sh` can no longer probe a TLS port the stack owns, because the
stack owns none. It asks the published loopback ports over plain HTTP. This
narrows what it proves, honestly: it already declared that public DNS and TLS
were `verify_public.py`'s subject, and now it cannot accidentally appear to
cover them.

A deployment host that publishes 80 and 443 itself must now run a proxy of its
own. The stack no longer brings one, so a host with nothing in front of it
serves nothing. This is the cost of the decision and it is deliberate: the
supported topology is one where the host owns its own ports.

Local prod compose rehearsals keep working without any host configuration —
they reach the published loopback ports directly.

## Review conditions

Revisit if the stack is deployed to a host that owns its ports and has no
proxy, where a self-contained container that obtains its own certificate would
again be the shorter path.
