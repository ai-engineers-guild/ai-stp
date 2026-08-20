/* Generate HTML prototypes matched to localhost:3000 live UI */
const fs = require("fs");
const path = require("path");
const pagesDir = path.join(__dirname, "pages");

const ICONS = {
  moon:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-icon-moon aria-hidden="true"><path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"/></svg>',
  sun:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-icon-sun hidden aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
  user:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>',
  back:
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>',
};

function header(active) {
  const catalogClass = active === "catalog" ? "nav-link is-active" : "nav-link";
  return `
    <a href="#main-content" class="sr-only">Skip to content</a>
    <header class="topbar" data-od-id="site-header">
      <div class="topbar-inner">
        <nav class="nav" aria-label="Primary">
          <a href="landing.html" class="brand"><img src="../shared/brand/logo-mark.png" alt="" width="28" height="28" aria-hidden="true">ai_stp</a>
          <a href="catalog.html" class="${catalogClass}" title="Browse published components and setups">Catalog</a>
        </nav>
        <div class="top-actions">
          <label class="sr-only" for="locale-select">Language</label>
          <select id="locale-select" class="locale-select" aria-label="Language">
            <option value="ru">ru</option>
            <option value="en" selected>en</option>
          </select>
          <button type="button" class="icon-btn" data-action="theme" data-theme-label data-od-id="theme-toggle" aria-label="Dark">
            ${ICONS.moon}${ICONS.sun}
          </button>
          <a class="icon-btn outline" href="login.html" title="Sign in to your account" aria-label="Sign in">${ICONS.user}</a>
        </div>
      </div>
    </header>`;
}

function footer() {
  return `
    <footer class="footer" data-od-id="site-footer">
      <div class="footer-inner">
        <div>ai_stp · setup passports</div>
        <nav class="footer-links" aria-label="Site policies">
          <a href="docs.html">Documentation</a>
          <a href="legal-privacy.html">Privacy</a>
          <a href="legal-cookies.html">Cookies</a>
          <a href="legal-service-rules.html">Service rules</a>
          <a href="legal-licensing.html">Licensing</a>
        </nav>
      </div>
    </footer>`;
}

function page({ file, title, route, active, body }) {
  return `<!doctype html>
<html lang="en" class="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <link rel="stylesheet" href="../shared/tokens.css" />
  <link rel="stylesheet" href="../shared/ui.css" />
</head>
<body>
  <div class="shell" data-od-id="page-${file.replace(".html", "")}">
${header(active)}
    <main class="main" id="main-content">
${body}
    </main>
${footer()}
  </div>
  <div class="proto-note">prototype · ${route}</div>
  <script src="../shared/shell.js"></script>
</body>
</html>
`;
}

const components = [
  { name: "river-planner-agent", kind: "agent", art: "agent", desc: "Planning subagent for Pi documentation projects.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", harness: "pi", tags: ["planning", "documentation"], support: "beta · missing", lane: "experimental", href: "component.html" },
  { name: "river-session-hook", kind: "hook", art: "hook", desc: "Session lifecycle hook for Pi documentation runs.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", harness: "pi", tags: ["documentation", "devops"], support: "beta · missing", lane: "experimental", href: "component.html" },
  { name: "river-docs-mcp", kind: "mcp", art: "mcp", desc: "Documentation MCP server for the Pi harness.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", harness: "pi", tags: ["documentation"], support: "beta · missing", lane: "experimental", href: "component.html" },
  { name: "river-research-skill", kind: "skill", art: "skill", desc: "Research synthesis skill for the Pi harness.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", harness: "pi", tags: ["documentation", "planning"], support: "beta · missing", lane: "experimental", href: "component.html" },
  { name: "river-docs-skill", kind: "skill", art: "skill", desc: "Documentation writing skill for the Pi harness.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", harness: "pi", tags: ["documentation"], support: "beta · missing", lane: "experimental", href: "component.html" },
  { name: "northwind-review-agent", kind: "agent", art: "agent", desc: "Code-review subagent for Codex pull requests.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA0", harness: "codex", tags: ["code-review", "python"], support: "primary · missing", lane: "experimental", href: "component.html" },
  { name: "northwind-precommit-hook", kind: "hook", art: "hook", desc: "Pre-commit hook for Codex Python workspaces.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA0", harness: "codex", tags: ["python", "devops"], support: "primary · missing", lane: "experimental", href: "component.html" },
  { name: "northwind-github-mcp", kind: "mcp", art: "mcp", desc: "GitHub MCP server for the Codex harness.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA0", harness: "codex", tags: ["github", "devops"], support: "primary · missing", lane: "experimental", href: "component.html" },
  { name: "firstparty-audit-hook", kind: "hook", art: "hook", desc: "Audit lifecycle hook for Claude Code sessions.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z", harness: "claude-code", tags: ["security", "devops"], support: "primary · missing", lane: "experimental", href: "component.html" },
];

const setups = [
  { name: "river-docs-workspace", desc: "Pi workspace: docs MCP, session hook, docs and research skills.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", harness: "pi", purpose: "documentation", role: "technical-writer", tags: ["documentation", "planning"], support: "beta · missing", lane: "experimental" },
  { name: "northwind-python-workspace", desc: "Codex workspace: GitHub MCP, precommit hook, refactor and test skills.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3YA0", harness: "codex", purpose: "python-development", role: "developer", tags: ["python", "code-review"], support: "primary · missing", lane: "experimental" },
  { name: "firstparty-ops-workspace", desc: "Claude Code ops workspace: metrics MCP, audit hook, security and release skills.", pub: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z", harness: "claude-code", purpose: "operations", role: "platform-engineer", tags: ["devops", "security"], support: "primary · missing", lane: "experimental" },
  { name: "fixture-setup", desc: "fixture-setup-description", pub: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z", harness: "claude-code", purpose: "fixture-purpose", role: "fixture-role", tags: ["python"], support: "primary · missing", lane: "experimental" },
];

function componentCard(c) {
  return `<li><article class="card" data-kind="component">
  <div class="card-body">
    <img class="card-media" src="../shared/catalog-art/${c.art}.webp" alt="" width="320" height="180">
    <div class="stack-sm" style="gap:0.75rem;flex:1">
      <div class="row" style="justify-content:space-between;align-items:flex-start">
        <div class="stack-sm" style="gap:0.25rem;min-width:0">
          <p class="mono muted" style="margin:0;font-size:11px;font-weight:500;letter-spacing:.04em;text-transform:uppercase">Component · ${c.kind}</p>
          <h3><a href="${c.href}">${c.name}</a></h3>
        </div>
        <div class="row" style="gap:0.25rem;justify-content:flex-end">
          <span class="chip chip-secondary">${c.lane}</span>
          <span class="chip">${c.support}</span>
          <span class="chip">${c.harness}</span>
        </div>
      </div>
      <p>${c.desc}</p>
      <div class="row muted text-xs" style="gap:1rem">
        <span>Publisher: <a class="mono underline" style="position:relative;z-index:1" href="publisher.html">${c.pub}</a></span>
        <span>Updated: <time datetime="2026-08-06">8/6/2026</time></span>
        <span>Likes: 0</span>
      </div>
      <dl class="card-meta">
        <div><dt>Version</dt><dd class="mono">1.0</dd></div>
        <div><dt>Type</dt><dd>${c.kind}</dd></div>
        <div style="grid-column:1/-1"><dt>Harness</dt><dd>${c.harness}</dd></div>
      </dl>
      <div class="row" style="gap:0.25rem">${c.tags.map((t) => `<span class="chip">${t}</span>`).join("")}</div>
      <div class="card-foot">
        <span>Author verified: No</span>
        <span>Component verified: No</span>
        <span>Support tier: ${c.support.split(" · ")[0]}</span>
        <span>Support state: ${c.support.split(" · ")[1] || "missing"}</span>
        <span>Support evidence: none</span>
      </div>
    </div>
  </div>
</article></li>`;
}

function setupCard(s) {
  return `<li><article class="card" data-kind="setup">
  <div class="card-body">
    <img class="card-media" src="../shared/catalog-art/setup.webp" alt="" width="320" height="180">
    <div class="stack-sm" style="gap:0.75rem;flex:1">
      <div class="row" style="justify-content:space-between;align-items:flex-start">
        <div class="stack-sm" style="gap:0.25rem;min-width:0">
          <p class="mono muted" style="margin:0;font-size:11px;font-weight:500;letter-spacing:.04em;text-transform:uppercase">Setup</p>
          <h3><a href="setup.html">${s.name}</a></h3>
        </div>
        <div class="row" style="gap:0.25rem;justify-content:flex-end">
          <span class="chip chip-secondary">${s.lane}</span>
          <span class="chip">${s.support}</span>
          <span class="chip">${s.harness}</span>
        </div>
      </div>
      <p>${s.desc}</p>
      <div class="row muted text-xs" style="gap:1rem">
        <span>Publisher: <a class="mono underline" style="position:relative;z-index:1" href="publisher.html">${s.pub}</a></span>
        <span>Updated: <time datetime="2026-08-06">8/6/2026</time></span>
        <span>Likes: 0</span>
      </div>
      <dl class="card-meta">
        <div><dt>Version</dt><dd class="mono">1.0</dd></div>
        <div><dt>Harness</dt><dd>${s.harness}</dd></div>
        <div><dt>Purpose</dt><dd>${s.purpose}</dd></div>
        <div><dt>Target role</dt><dd>${s.role}</dd></div>
      </dl>
      <div class="row" style="gap:0.25rem">${s.tags.map((t) => `<span class="chip">${t}</span>`).join("")}</div>
      <div class="card-foot">
        <span>Author verified: No</span>
        <span>Component verified: No</span>
        <span>Support tier: ${s.support.split(" · ")[0]}</span>
        <span>Support state: ${s.support.split(" · ")[1] || "missing"}</span>
        <span>Support evidence: none</span>
      </div>
    </div>
  </div>
</article></li>`;
}

const pages = {};

pages["landing.html"] = page({
  file: "landing.html",
  title: "ai_stp",
  route: "/",
  active: "home",
  body: `
<div class="stack">
  <section class="hero-grid">
    <div class="stack-md">
      <img class="logo-lockup" src="../shared/brand/logo-lockup.svg" alt="ai_stp">
      <p class="eyebrow">Five in the loop — a human crew group</p>
      <h1>One setup for every coding harness</h1>
      <p class="lede">Browse verified components and setups, install the CLI, and keep local and cloud state aligned.</p>
      <div class="row">
        <a class="btn btn-primary" href="catalog.html">Browse catalog</a>
        <a class="btn btn-outline" href="login.html">Sign in</a>
      </div>
    </div>
    <div class="hero-media" aria-label="ai_stp workflow preview">
      <img src="../shared/brand/hero-preview-poster.png" alt="">
      <div class="hero-media-fade"></div>
      <div class="hero-media-caption">Discover · verify · assemble · apply</div>
    </div>
  </section>
  <section class="panel stack-sm" aria-labelledby="install-heading">
    <h2 id="install-heading">Install the CLI</h2>
    <p class="lede-sm">Run this command exactly. It comes from a single canonical module.</p>
    <div class="row" style="align-items:stretch">
      <code class="codebox">uv tool install ai-stp-cli</code>
      <button type="button" class="btn btn-secondary" data-action="copy" data-copy="uv tool install ai-stp-cli">Copy</button>
    </div>
    <div>
      <h3 class="text-sm" style="font-weight:500">Prerequisites</h3>
      <ul class="list-disc">
        <li><code>uv</code></li>
        <li><code>python&gt;=3.12</code></li>
      </ul>
    </div>
  </section>
</div>`,
});

pages["catalog.html"] = page({
  file: "catalog.html",
  title: "Catalog · ai_stp",
  route: "/catalog",
  active: "catalog",
  body: `
<div class="stack-lg">
  <div class="stack-sm" style="gap:0.5rem">
    <h1 style="font-size:1.875rem">Catalog</h1>
    <p class="lede-sm">Browse components and full setups. Experimental seed is included by default so the first-party corpus is visible without an extra click.</p>
  </div>
  <form class="stack-sm" role="search" onsubmit="return false">
    <div class="toolbar">
      <details class="search-details">
        <summary class="btn btn-primary">Search</summary>
        <div class="search-panel">
          <div class="field">
            <label for="catalog-search">Search</label>
            <div class="row">
              <input id="catalog-search" type="search" placeholder="Search components and setups" style="flex:1">
              <button class="btn btn-primary" type="submit">Search</button>
            </div>
          </div>
        </div>
      </details>
      <button class="btn btn-outline" type="button">Filters</button>
      <div class="seg" aria-label="Sort results">
        <a href="catalog.html" aria-current="true">Relevance</a>
        <a href="catalog.html">Recently updated</a>
        <a href="catalog.html">Most liked</a>
      </div>
      <div class="seg" aria-label="Result layout">
        <a href="catalog.html" aria-current="true">Cards</a>
        <a href="catalog.html">List</a>
      </div>
    </div>
  </form>
  <section>
    <div class="row" style="justify-content:space-between;align-items:flex-end;margin-bottom:1rem">
      <div>
        <h2>Components</h2>
        <p class="lede-sm" style="margin-top:0.25rem">Authoritative and experimental lanes are merged here. Author verification is not a content-safety proof.</p>
      </div>
      <p class="mono muted text-sm" aria-live="polite">${components.length}</p>
    </div>
    <ul class="grid-3" style="list-style:none;margin:0;padding:0">
      ${components.map(componentCard).join("")}
    </ul>
  </section>
  <section>
    <div class="row" style="justify-content:space-between;align-items:flex-end;margin-bottom:1rem">
      <div>
        <h2>Setups</h2>
        <p class="lede-sm" style="margin-top:0.25rem">Authoritative and experimental lanes are merged here. Author verification is not a content-safety proof.</p>
      </div>
      <p class="mono muted text-sm" aria-live="polite">${setups.length}</p>
    </div>
    <ul class="grid-3" style="list-style:none;margin:0;padding:0">
      ${setups.map(setupCard).join("")}
    </ul>
  </section>
</div>`,
});

pages["login.html"] = page({
  file: "login.html",
  title: "Sign in · ai_stp",
  route: "/login",
  active: "login",
  body: `
<div class="narrow stack" style="gap:1.5rem">
  <div class="stack-sm" style="gap:0.5rem">
    <h1 style="font-size:1.875rem">Sign in</h1>
    <p class="muted">Sign in with a supported provider. Session state is stored in a secure HttpOnly cookie.</p>
  </div>
  <div class="stack-sm">
    <a class="btn btn-primary btn-block" href="account.html">Continue with Google</a>
    <a class="btn btn-secondary btn-block" href="account.html">Continue with GitHub</a>
  </div>
</div>`,
});

pages["docs.html"] = page({
  file: "docs.html",
  title: "Documentation · ai_stp",
  route: "/docs",
  active: "docs",
  body: `
<div class="docs-layout">
  <aside class="docs-nav stack-sm" style="gap:0.5rem" aria-label="Documentation sections">
    <a href="#overview">Product overview</a>
    <a href="#cli">CLI and agent quickstart</a>
    <a href="#api">API and contracts</a>
    <a href="#trust">Trust and security</a>
    <a href="#operations">Operations</a>
    <a href="#authors">Docs for authors</a>
  </aside>
  <article class="stack-lg">
    <header class="stack-sm" style="gap:0.5rem">
      <p class="mono muted" style="margin:0;font-size:11px;letter-spacing:.04em;text-transform:uppercase">source: repository docs · revision pending import</p>
      <h1 style="font-size:1.875rem">Documentation</h1>
      <p class="lede-sm">Technical docs for people and agents. Source revisions are imported from the repository.</p>
    </header>
    <section id="overview" class="stack-sm" style="gap:0.5rem">
      <h2>Product overview</h2>
      <p class="lede-sm">ai_stp publishes setup passports for coding harnesses with explicit trust lanes.</p>
    </section>
    <section id="cli" class="stack-sm" style="gap:0.5rem">
      <h2>CLI and agent quickstart</h2>
      <p class="lede-sm">Install the CLI, authorize a device, then sync or show objects with registry commands.</p>
    </section>
    <section id="api" class="stack-sm" style="gap:0.5rem">
      <h2>API and contracts</h2>
      <p class="lede-sm">HTTP API and machine contracts live under docs/contracts and OpenAPI.</p>
    </section>
    <section id="trust" class="stack-sm" style="gap:0.5rem">
      <h2>Trust and security</h2>
      <p class="lede-sm">Author verification is independent of content safety. Experimental is request-scoped.</p>
    </section>
    <section id="operations" class="stack-sm" style="gap:0.5rem">
      <h2>Operations</h2>
      <p class="lede-sm">Health, backups, and recovery runbooks live under docs/operations.</p>
    </section>
    <section id="authors" class="stack-sm" style="gap:0.5rem">
      <h2>Docs for authors</h2>
      <p class="lede-sm">Authors publish through CLI validation; the web does not edit passport composition.</p>
    </section>
    <p class="text-sm"><a class="underline" href="catalog.html">Open catalog</a></p>
  </article>
</div>`,
});

function legal(slug, title, body) {
  return page({
    file: slug,
    title: title + " · ai_stp",
    route: "/legal/" + slug.replace("legal-", "").replace(".html", ""),
    active: "legal",
    body: `
<article class="mid stack" style="gap:1.5rem">
  <p class="text-sm"><a class="underline" href="landing.html">Back to home</a></p>
  <header class="stack-sm" style="gap:0.5rem">
    <h1 style="font-size:1.875rem">${title}</h1>
    <dl class="row mono muted text-xs" style="gap:1rem;margin:0">
      <div><dt style="display:inline">Version: </dt><dd style="display:inline">1.0</dd></div>
      <div><dt style="display:inline">Effective: </dt><dd style="display:inline">2026-08-05</dd></div>
      <div><dt style="display:inline">Language: </dt><dd style="display:inline">en</dd></div>
    </dl>
  </header>
  <div class="stack-sm">
    <h2 style="font-size:1.125rem">Contents</h2>
    <p class="lede-sm">${body}</p>
  </div>
</article>`,
  });
}

pages["legal-privacy.html"] = legal(
  "legal-privacy.html",
  "Privacy",
  "How account and device data are processed to provide catalog access. Full published policy text is served from versioned revisions."
);
pages["legal-cookies.html"] = legal(
  "legal-cookies.html",
  "Cookies",
  "Session and preference cookies required to operate the signed-in shell."
);
pages["legal-service-rules.html"] = legal(
  "legal-service-rules.html",
  "Service rules",
  "Acceptable use of the platform and publication surface."
);
pages["legal-licensing.html"] = legal(
  "legal-licensing.html",
  "Licensing / author content responsibility",
  "Platform licensing is separate from author content. Authors are responsible for rights and do not receive a platform content-safety guarantee."
);

pages["component.html"] = page({
  file: "component.html",
  title: "river-planner-agent · ai_stp",
  route: "/catalog/components/[id]",
  active: "catalog",
  body: `
<article class="wide stack-md">
  <a class="back-link" href="catalog.html">${ICONS.back}Back to catalog</a>
  <div class="row" style="align-items:flex-start;gap:1rem">
    <img src="../shared/catalog-art/agent.webp" alt="" width="56" height="56" style="width:3.5rem;height:3.5rem;border-radius:var(--radius-lg);object-fit:cover;background:hsl(var(--muted))">
    <div class="stack-sm" style="gap:0.5rem;min-width:0">
      <h1 style="font-size:1.875rem">river-planner-agent</h1>
      <div class="row" style="gap:0.5rem">
        <span class="chip chip-primary">experimental</span>
        <span class="chip chip-secondary">agent</span>
        <span class="chip">pi</span>
      </div>
    </div>
  </div>
  <section class="stack-sm">
    <div class="row" style="justify-content:space-between">
      <h2>Description</h2>
      <span class="mono muted text-xs">v1.0</span>
    </div>
    <p class="lede-sm">Planning subagent for Pi documentation projects.</p>
  </section>
  <dl class="dl dl-3 panel" style="padding:1rem">
    <div><dt>Version</dt><dd>1.0</dd></div>
    <div><dt>Lifecycle</dt><dd>active</dd></div>
    <div><dt>Harness</dt><dd>pi</dd></div>
    <div><dt>Type</dt><dd>agent</dd></div>
    <div><dt>Projection</dt><dd>native_files</dd></div>
    <div><dt>Published</dt><dd>2026-08-05T00:00:00.000Z</dd></div>
    <div><dt>Author verified</dt><dd>No</dd></div>
    <div><dt>Component verified</dt><dd>No</dd></div>
    <div class="span-2"><dt>Publisher</dt><dd><a class="mono underline text-sm" href="publisher.html">account_01JQZK7B8N4M6P2R9T5V0X3YA1</a></dd></div>
    <div class="span-2"><dt>Tags</dt><dd class="row" style="gap:0.25rem;margin-top:0.25rem"><span class="chip">planning</span><span class="chip">documentation</span></dd></div>
  </dl>
  <section class="stack-sm">
    <h2>Support evidence</h2>
    <dl class="dl text-sm">
      <div><dt class="muted">Support tier</dt><dd><span class="chip">beta</span></dd></div>
      <div><dt class="muted">Support state</dt><dd><span class="chip chip-secondary">missing</span></dd></div>
      <div class="span-2"><dt class="muted">Support evidence</dt><dd>none</dd></div>
    </dl>
  </section>
  <section class="stack-sm">
    <h2>Compatibility</h2>
    <dl class="dl text-sm">
      <div><dt class="muted">Requires credentials</dt><dd>No</dd></div>
      <div><dt class="muted">Requires authorization</dt><dd>none</dd></div>
      <div><dt class="muted">License</dt><dd>AGPL-3.0-or-later</dd></div>
      <div><dt class="muted">Checks and evidence</dt><dd>No evidence refs published</dd></div>
    </dl>
  </section>
  <section>
    <h2>Offered versions</h2>
    <p class="lede-sm" style="margin-top:0.25rem">Version numbers may be non-contiguous; missing numbers are intentional.</p>
    <ul style="list-style:none;margin:0.75rem 0 0;padding:0" class="stack-sm">
      <li class="version-item"><a href="component-preview.html">1.0</a><span class="muted text-sm" style="margin-left:0.5rem">active · experimental · beta · missing</span></li>
    </ul>
  </section>
  <section class="panel stack-sm">
    <h2 style="font-size:1rem">Use via CLI</h2>
    <p class="lede-sm">Command uses the stable object id and version.</p>
    <div class="row" style="align-items:stretch">
      <code class="codebox codebox-sm">ai-stp registry show component_01JQZK7B8N4M6P2R9T5V0X3YBE@1.0</code>
      <button type="button" class="btn btn-secondary" data-action="copy" data-copy="ai-stp registry show component_01JQZK7B8N4M6P2R9T5V0X3YBE@1.0">Copy</button>
    </div>
    <p class="muted text-sm"><a class="underline" href="docs.html">CLI documentation</a></p>
  </section>
</article>`,
});

pages["setup.html"] = page({
  file: "setup.html",
  title: "river-docs-workspace · ai_stp",
  route: "/catalog/setups/[id]",
  active: "catalog",
  body: `
<article class="wide stack-md">
  <a class="back-link" href="catalog.html">${ICONS.back}Back to catalog</a>
  <div class="row" style="align-items:flex-start;gap:1rem">
    <img src="../shared/catalog-art/setup.webp" alt="" width="56" height="56" style="width:3.5rem;height:3.5rem;border-radius:var(--radius-lg);object-fit:cover;background:hsl(var(--muted))">
    <div class="stack-sm" style="gap:0.5rem;min-width:0">
      <h1 style="font-size:1.875rem">river-docs-workspace</h1>
      <div class="row" style="gap:0.5rem">
        <span class="chip chip-primary">experimental</span>
        <span class="chip chip-secondary">setup</span>
        <span class="chip">pi</span>
      </div>
    </div>
  </div>
  <section class="stack-sm">
    <div class="row" style="justify-content:space-between">
      <h2>Description</h2>
      <span class="mono muted text-xs">v1.0</span>
    </div>
    <p class="lede-sm">Pi workspace: docs MCP, session hook, docs and research skills.</p>
  </section>
  <dl class="dl dl-3 panel" style="padding:1rem">
    <div><dt>Version</dt><dd>1.0</dd></div>
    <div><dt>Lifecycle</dt><dd>active</dd></div>
    <div><dt>Harness</dt><dd>pi</dd></div>
    <div><dt>Purpose</dt><dd>documentation</dd></div>
    <div><dt>Target role</dt><dd>technical-writer</dd></div>
    <div><dt>Published</dt><dd>2026-08-05T00:00:00.000Z</dd></div>
    <div><dt>Author verified</dt><dd>No</dd></div>
    <div><dt>Component verified</dt><dd>No</dd></div>
    <div class="span-2"><dt>Publisher</dt><dd><a class="mono underline text-sm" href="publisher.html">account_01JQZK7B8N4M6P2R9T5V0X3YA1</a></dd></div>
    <div class="span-2"><dt>Tags</dt><dd class="row" style="gap:0.25rem;margin-top:0.25rem"><span class="chip">documentation</span><span class="chip">planning</span></dd></div>
  </dl>
  <section class="stack-sm">
    <h2>Support evidence</h2>
    <dl class="dl text-sm">
      <div><dt class="muted">Support tier</dt><dd><span class="chip">beta</span></dd></div>
      <div><dt class="muted">Support state</dt><dd><span class="chip chip-secondary">missing</span></dd></div>
      <div class="span-2"><dt class="muted">Support evidence</dt><dd>none</dd></div>
    </dl>
  </section>
  <section>
    <h2>Offered versions</h2>
    <p class="lede-sm" style="margin-top:0.25rem">Version numbers may be non-contiguous; missing numbers are intentional.</p>
    <ul style="list-style:none;margin:0.75rem 0 0;padding:0" class="stack-sm">
      <li class="version-item"><a href="setup-preview.html">1.0</a><span class="muted text-sm" style="margin-left:0.5rem">active · experimental · beta · missing</span></li>
    </ul>
  </section>
  <section class="panel stack-sm">
    <h2 style="font-size:1rem">Use via CLI</h2>
    <p class="lede-sm">Command uses the stable object id and version.</p>
    <div class="row" style="align-items:stretch">
      <code class="codebox codebox-sm">ai-stp registry show setup_01JQZK7B8N4M6P2R9T5V0X3YBF@1.0</code>
      <button type="button" class="btn btn-secondary" data-action="copy" data-copy="ai-stp registry show setup_01JQZK7B8N4M6P2R9T5V0X3YBF@1.0">Copy</button>
    </div>
    <p class="muted text-sm"><a class="underline" href="docs.html">CLI documentation</a></p>
  </section>
</article>`,
});

pages["component-preview.html"] = page({
  file: "component-preview.html",
  title: "Preview · river-planner-agent · ai_stp",
  route: "/catalog/components/[id]/preview",
  active: "catalog",
  body: `
<article class="wide stack-md">
  <a class="back-link" href="component.html">${ICONS.back}Back to component</a>
  <header class="stack-sm" style="gap:0.5rem">
    <p class="eyebrow">Version preview · 1.0</p>
    <h1 style="font-size:1.875rem">river-planner-agent</h1>
    <p class="lede-sm">Read-only passport projection for the selected version.</p>
  </header>
  <div class="panel stack-sm">
    <h2 style="font-size:1rem">Passport summary</h2>
    <dl class="dl text-sm">
      <div><dt class="muted">Kind</dt><dd>component / agent</dd></div>
      <div><dt class="muted">Harness</dt><dd>pi</dd></div>
      <div><dt class="muted">Projection</dt><dd>native_files</dd></div>
      <div><dt class="muted">License</dt><dd>AGPL-3.0-or-later</dd></div>
    </dl>
  </div>
  <div class="panel stack-sm">
    <h2 style="font-size:1rem">Files (preview)</h2>
    <ul class="mono text-sm muted" style="margin:0;padding-left:1.25rem">
      <li>AGENTS.md</li>
      <li>manifest.json</li>
      <li>README.md</li>
    </ul>
  </div>
</article>`,
});

pages["setup-preview.html"] = page({
  file: "setup-preview.html",
  title: "Preview · river-docs-workspace · ai_stp",
  route: "/catalog/setups/[id]/preview",
  active: "catalog",
  body: `
<article class="wide stack-md">
  <a class="back-link" href="setup.html">${ICONS.back}Back to setup</a>
  <header class="stack-sm" style="gap:0.5rem">
    <p class="eyebrow">Version preview · 1.0</p>
    <h1 style="font-size:1.875rem">river-docs-workspace</h1>
    <p class="lede-sm">Read-only setup passport for the selected version.</p>
  </header>
  <div class="panel stack-sm">
    <h2 style="font-size:1rem">Composition</h2>
    <ul class="text-sm" style="margin:0;padding-left:1.25rem;color:hsl(var(--muted-foreground))">
      <li>river-docs-mcp @ 1.0</li>
      <li>river-session-hook @ 1.0</li>
      <li>river-docs-skill @ 1.0</li>
      <li>river-research-skill @ 1.0</li>
    </ul>
  </div>
</article>`,
});

pages["component-edit.html"] = page({
  file: "component-edit.html",
  title: "Edit · component · ai_stp",
  route: "/catalog/components/[id]/edit",
  active: "catalog",
  body: `
<article class="mid stack-md">
  <a class="back-link" href="component.html">${ICONS.back}Back</a>
  <h1 style="font-size:1.875rem">Edit component metadata</h1>
  <p class="lede-sm">Web does not rewrite passport composition. Metadata fields only.</p>
  <form class="panel stack-md" onsubmit="return false">
    <div class="field"><label for="c-name">Display name</label><input id="c-name" value="river-planner-agent"></div>
    <div class="field"><label for="c-desc">Description</label><textarea id="c-desc" style="height:6rem;padding:0.75rem">Planning subagent for Pi documentation projects.</textarea></div>
    <div class="field"><label for="c-tags">Tags</label><input id="c-tags" value="planning, documentation"></div>
    <div class="row"><button class="btn btn-primary" type="submit">Save</button><a class="btn btn-outline" href="component.html">Cancel</a></div>
  </form>
</article>`,
});

pages["setup-edit.html"] = page({
  file: "setup-edit.html",
  title: "Edit · setup · ai_stp",
  route: "/catalog/setups/[id]/edit",
  active: "catalog",
  body: `
<article class="mid stack-md">
  <a class="back-link" href="setup.html">${ICONS.back}Back</a>
  <h1 style="font-size:1.875rem">Edit setup metadata</h1>
  <p class="lede-sm">Web does not rewrite passport composition. Metadata fields only.</p>
  <form class="panel stack-md" onsubmit="return false">
    <div class="field"><label for="s-name">Display name</label><input id="s-name" value="river-docs-workspace"></div>
    <div class="field"><label for="s-desc">Description</label><textarea id="s-desc" style="height:6rem;padding:0.75rem">Pi workspace: docs MCP, session hook, docs and research skills.</textarea></div>
    <div class="field"><label for="s-role">Target role</label><input id="s-role" value="technical-writer"></div>
    <div class="row"><button class="btn btn-primary" type="submit">Save</button><a class="btn btn-outline" href="setup.html">Cancel</a></div>
  </form>
</article>`,
});

pages["publisher.html"] = page({
  file: "publisher.html",
  title: "Publisher · ai_stp",
  route: "/publishers/[account]",
  active: "catalog",
  body: `
<article class="wide stack-lg">
  <header class="stack-sm" style="gap:0.5rem">
    <p class="eyebrow">Publisher</p>
    <h1 style="font-size:1.875rem">account_01JQZK7B8N4M6P2R9T5V0X3YA1</h1>
    <p class="lede-sm">Published components and setups from this account.</p>
  </header>
  <section>
    <div class="row" style="justify-content:space-between;margin-bottom:1rem">
      <h2>Objects</h2>
      <span class="mono muted text-sm">5</span>
    </div>
    <ul class="grid-3" style="list-style:none;margin:0;padding:0">
      ${components.filter((c) => c.pub === "account_01JQZK7B8N4M6P2R9T5V0X3YA1").map(componentCard).join("")}
      ${setups.filter((s) => s.pub === "account_01JQZK7B8N4M6P2R9T5V0X3YA1").map(setupCard).join("")}
    </ul>
  </section>
</article>`,
});

pages["account.html"] = page({
  file: "account.html",
  title: "Account · ai_stp",
  route: "/account",
  active: "account",
  body: `
<div class="stack-lg">
  <header class="stack-sm" style="gap:0.5rem">
    <h1 style="font-size:1.875rem">Account</h1>
    <p class="lede-sm">Signed-in shell. Session is cookie-backed.</p>
  </header>
  <div class="grid-2">
    <a class="card" href="profile.html" style="padding:1rem;text-decoration:none">
      <div class="card-body" style="padding:0">
        <h3>Profile</h3>
        <p>Display name, handle, and public publisher surface.</p>
      </div>
    </a>
    <a class="card" href="privacy.html" style="padding:1rem;text-decoration:none">
      <div class="card-body" style="padding:0">
        <h3>Privacy</h3>
        <p>Visibility and data controls for your account.</p>
      </div>
    </a>
    <a class="card" href="devices.html" style="padding:1rem;text-decoration:none">
      <div class="card-body" style="padding:0">
        <h3>Devices</h3>
        <p>CLI device authorizations linked to this account.</p>
      </div>
    </a>
  </div>
  <div class="panel stack-sm">
    <h2 style="font-size:1rem">Session</h2>
    <dl class="dl text-sm">
      <div><dt class="muted">Account id</dt><dd class="mono">account_01JQZK7B8N4M6P2R9T5V0X3YZZ</dd></div>
      <div><dt class="muted">Email</dt><dd>you@example.com</dd></div>
      <div><dt class="muted">Providers</dt><dd>Google</dd></div>
    </dl>
    <div class="row"><a class="btn btn-outline" href="landing.html">Sign out</a></div>
  </div>
</div>`,
});

pages["account-empty.html"] = page({
  file: "account-empty.html",
  title: "Account · ai_stp",
  route: "/account (empty)",
  active: "account",
  body: `
<div class="center-page">
  <h1 style="font-size:1.875rem">No account session</h1>
  <p class="lede-sm" style="text-align:center">Sign in to manage profile, privacy, and devices.</p>
  <a class="btn btn-primary" href="login.html">Sign in</a>
</div>`,
});

pages["profile.html"] = page({
  file: "profile.html",
  title: "Profile · ai_stp",
  route: "/account/profile",
  active: "account",
  body: `
<article class="mid stack-md">
  <a class="back-link" href="account.html">${ICONS.back}Account</a>
  <header class="stack-sm" style="gap:0.5rem">
    <h1 style="font-size:1.875rem">Public profile</h1>
    <p class="lede-sm">Display name, short bio, links, and avatar for your public publisher page.</p>
  </header>
  <form class="panel stack-md" onsubmit="return false" style="gap:1.25rem">
    <div class="row" style="justify-content:space-between;align-items:center">
      <span class="chip mono">published</span>
      <a class="btn btn-outline btn-sm" href="profile-preview.html">Preview</a>
    </div>
    <div class="row" style="align-items:flex-start;gap:1rem">
      <div class="avatar-lg" aria-hidden="true" style="width:5rem;height:5rem;border-radius:999px;border:1px solid var(--border);background:var(--muted);display:grid;place-items:center;color:var(--muted-fg)">
        ${ICONS.user || ICONS.account || "·"}
      </div>
      <div class="stack-sm" style="gap:0.5rem;flex:1">
        <p class="muted text-sm" style="margin:0">JPEG, PNG or WebP up to 5 MB. A square image of at least 512 × 512 px is recommended.</p>
        <p class="muted text-sm" style="margin:0;font-weight:500">From your sign-in methods</p>
        <div class="row" style="flex-wrap:wrap;gap:0.5rem">
          <button type="button" class="btn btn-outline btn-sm">Upload photo</button>
          <button type="button" class="btn btn-outline btn-sm">Use from GitHub</button>
          <button type="button" class="btn btn-outline btn-sm">Use from Google</button>
        </div>
      </div>
    </div>
    <div class="field"><label for="p-name">Display name</label><input id="p-name" value="You" maxlength="80"></div>
    <div class="field">
      <div class="row" style="justify-content:space-between;align-items:center;margin-bottom:0.35rem">
        <label for="p-bio" style="margin:0">Short bio</label>
        <div class="row" style="gap:0.25rem">
          <button type="button" class="btn btn-secondary btn-sm" aria-pressed="true">Plain text</button>
          <button type="button" class="btn btn-outline btn-sm">Rendered</button>
        </div>
      </div>
      <textarea id="p-bio" style="height:7rem;padding:0.75rem;font-family:var(--font-mono, ui-monospace, monospace)">Building setup passports.</textarea>
      <p class="muted mono text-sm" style="margin:0.35rem 0 0">Limited Markdown (lists, headings, emoji, tables, links, bold, code) · 25/1500</p>
    </div>
    <div class="stack-sm">
      <div class="row" style="justify-content:space-between;align-items:center">
        <h2 style="font-size:0.875rem;margin:0">Links</h2>
        <button type="button" class="btn btn-outline btn-sm">Add</button>
      </div>
      <p class="muted text-sm" style="margin:0">No links yet. Add up to eight HTTPS links.</p>
    </div>
    <div class="row" style="justify-content:space-between;align-items:center;border-top:1px solid var(--border);padding-top:1rem;flex-wrap:wrap;gap:0.75rem">
      <p class="muted text-sm" style="margin:0;max-width:28rem">Changes go live only when you press Save changes. Preview is temporary and not saved.</p>
      <div class="row" style="gap:0.5rem">
        <a class="btn btn-outline" href="profile-preview.html">Preview</a>
        <button class="btn btn-primary" type="submit">Save changes</button>
      </div>
    </div>
  </form>
</article>`,
});

pages["profile-preview.html"] = page({
  file: "profile-preview.html",
  title: "Profile preview · ai_stp",
  route: "/account/profile/preview",
  active: "account",
  body: `
<article class="mid stack-md">
  <a class="back-link" href="profile.html">${ICONS.back}Edit profile</a>
  <header class="stack-sm" style="gap:0.5rem">
    <p class="eyebrow">Public preview</p>
    <h1 style="font-size:1.875rem">You</h1>
    <p class="mono muted text-sm">@you</p>
    <p class="lede-sm">Building setup passports.</p>
  </header>
  <div class="panel"><p class="muted text-sm" style="margin:0">No public publications yet.</p></div>
</article>`,
});

pages["privacy.html"] = page({
  file: "privacy.html",
  title: "Privacy · ai_stp",
  route: "/account/privacy",
  active: "account",
  body: `
<article class="mid stack-md">
  <a class="back-link" href="account.html">${ICONS.back}Account</a>
  <h1 style="font-size:1.875rem">Privacy</h1>
  <p class="lede-sm">Controls for account visibility and data retention.</p>
  <div class="panel stack-md">
    <label class="row" style="justify-content:space-between">
      <span class="text-sm">Show profile publicly</span>
      <input type="checkbox" checked>
    </label>
    <label class="row" style="justify-content:space-between">
      <span class="text-sm">Allow publisher listing</span>
      <input type="checkbox" checked>
    </label>
    <button class="btn btn-primary" type="button">Save preferences</button>
  </div>
</article>`,
});

pages["devices.html"] = page({
  file: "devices.html",
  title: "Devices · ai_stp",
  route: "/devices",
  active: "account",
  body: `
<div class="stack-lg">
  <header class="stack-sm" style="gap:0.5rem">
    <h1 style="font-size:1.875rem">Devices</h1>
    <p class="lede-sm">CLI device authorizations linked to your account.</p>
  </header>
  <div class="panel stack-sm">
    <div class="row" style="justify-content:space-between">
      <div>
        <div class="text-sm" style="font-weight:500">workstation-main</div>
        <div class="mono muted text-xs">device_01JQZK7B8N4M6P2R9T5V0X3YD1</div>
      </div>
      <span class="chip chip-secondary">active</span>
    </div>
    <div class="row muted text-xs" style="gap:1rem">
      <span>Created: 2026-08-05</span>
      <span>Last seen: 2026-08-09</span>
    </div>
    <button class="btn btn-outline btn-sm" type="button">Revoke</button>
  </div>
  <div class="panel stack-sm">
    <h2 style="font-size:1rem">Authorize a device</h2>
    <p class="lede-sm">Run <code class="mono text-xs">ai-stp auth device</code> in the CLI, then confirm the code here.</p>
    <div class="field"><label for="device-code">Device code</label><input id="device-code" class="mono" placeholder="ABCD-EFGH" style="letter-spacing:0.12em"></div>
    <button class="btn btn-primary" type="button">Confirm device</button>
  </div>
</div>`,
});

pages["not-found.html"] = page({
  file: "not-found.html",
  title: "404 · ai_stp",
  route: "/404",
  active: "error",
  body: `
<div class="center-page">
  <h1 style="font-size:3rem">404</h1>
  <p class="lede-sm">This page could not be found.</p>
  <a class="btn btn-primary" href="landing.html">Back to home</a>
</div>`,
});

pages["error-500.html"] = page({
  file: "error-500.html",
  title: "Error · ai_stp",
  route: "/500",
  active: "error",
  body: `
<div class="center-page">
  <h1 style="font-size:1.875rem">Something went wrong</h1>
  <p class="lede-sm">An unexpected error occurred. Try again or return home.</p>
  <div class="row">
    <button class="btn btn-primary" type="button" onclick="location.reload()">Retry</button>
    <a class="btn btn-outline" href="landing.html">Home</a>
  </div>
</div>`,
});

for (const [name, html] of Object.entries(pages)) {
  fs.writeFileSync(path.join(pagesDir, name), html, "utf8");
}

// Update index.html
const indexHtml = `<!doctype html>
<html lang="en" class="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ai_stp · HTML prototypes index</title>
  <link rel="stylesheet" href="./shared/tokens.css" />
  <link rel="stylesheet" href="./shared/ui.css" />
  <style>
    body { margin:0; min-height:100vh; font-family:var(--font-sans); background:hsl(var(--background)); color:hsl(var(--foreground)); padding:48px 24px; }
    .wrap { max-width:800px; margin:0 auto; }
    h1 { font-size:28px; font-weight:500; letter-spacing:-0.02em; margin:0 0 8px; }
    .intro { color:hsl(var(--muted-foreground)); margin:0 0 28px; line-height:1.5; }
    .section-title { font-family:var(--font-mono); font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:hsl(var(--muted-foreground)); margin:28px 0 12px; }
    .card { border:1px solid hsl(var(--border)); background:hsl(var(--card)); border-radius:8px; padding:14px 16px; margin-bottom:10px; }
    .card a { color:hsl(var(--foreground)); font-weight:500; text-decoration:none; }
    .card a:hover { color:hsl(var(--primary)); }
    .mono { font-family:var(--font-mono); font-size:11px; color:hsl(var(--muted-foreground)); margin-top:6px; }
    .row-actions { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; }
    .badge { display:inline-block; font-family:var(--font-mono); font-size:10px; letter-spacing:0.04em; text-transform:uppercase; color:hsl(var(--primary)); border:1px solid hsl(var(--primary)); border-radius:4px; padding:2px 6px; margin-left:8px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>ai_stp · HTML prototypes</h1>
    <p class="intro">Rebuilt 1:1 from live <code class="mono" style="color:inherit">localhost:3000</code> (Playwright screenshots + DOM). Shared tokens match <code class="mono" style="color:inherit">apps/web</code>.</p>
    <div class="row-actions">
      <a class="btn btn-primary" href="./pages/landing.html">Landing</a>
      <a class="btn btn-outline" href="./branding.html">Branding</a>
      <button type="button" class="btn btn-outline btn-sm" data-action="theme" data-theme-label aria-label="Dark">Theme</button>
    </div>
    <div class="card" style="border-color:hsl(var(--primary))">
      <a href="./branding.html">Branding / design tokens</a><span class="badge">brand</span>
      <div class="mono">branding.html · mark, color, type, rules</div>
    </div>
    <p class="section-title">Product screens (matched to live)</p>
    ${[
      ["landing.html", "Home", "/"],
      ["login.html", "Sign in", "/login"],
      ["catalog.html", "Catalog", "/catalog"],
      ["component.html", "Component detail", "/catalog/components/[id]"],
      ["setup.html", "Setup detail", "/catalog/setups/[id]"],
      ["component-preview.html", "Component preview", "version preview"],
      ["setup-preview.html", "Setup preview", "version preview"],
      ["component-edit.html", "Component edit", "metadata edit"],
      ["setup-edit.html", "Setup edit", "metadata edit"],
      ["publisher.html", "Publisher", "/publishers/[account]"],
      ["account.html", "Account", "/account"],
      ["account-empty.html", "Account · empty", "/account empty"],
      ["profile.html", "Profile", "/account/profile"],
      ["profile-preview.html", "Profile preview", "/account/profile/preview"],
      ["privacy.html", "Account privacy", "/account/privacy"],
      ["devices.html", "Devices", "/devices"],
      ["docs.html", "Documentation", "/docs"],
      ["legal-privacy.html", "Legal · Privacy", "/legal/privacy"],
      ["legal-cookies.html", "Legal · Cookies", "/legal/cookies"],
      ["legal-service-rules.html", "Legal · Service rules", "/legal/service-rules"],
      ["legal-licensing.html", "Legal · Licensing", "/legal/licensing"],
      ["not-found.html", "404", "/404"],
      ["error-500.html", "500", "/500"],
    ]
      .map(
        ([f, label, route]) => `<div class="card">
      <a href="./pages/${f}">${label}</a>
      <div class="mono">${route} · pages/${f}</div>
    </div>`
      )
      .join("\n    ")}
  </div>
  <script src="./shared/shell.js"></script>
</body>
</html>
`;
fs.writeFileSync(path.join(__dirname, "index.html"), indexHtml, "utf8");

console.log("Wrote", Object.keys(pages).length, "pages + index.html");
