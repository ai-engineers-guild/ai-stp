const fs = require("fs");
const path = require("path");
const ROOT = process.argv[2] || __dirname;
const PAGES = path.join(ROOT, "pages");
const SHARED = path.join(ROOT, "shared");
fs.mkdirSync(PAGES, { recursive: true });
fs.mkdirSync(SHARED, { recursive: true });

const FIX = {
  account: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  northwind: "account_01JQZK7B8N4M6P2R9T5V0X3YA0",
  hook: "component_01JQZK7B8N4M6P2R9T5V0X3YB3",
  skill: "component_01JQZK7B8N4M6P2R9T5V0X3YB5",
  setup: "setup_01JQZK7B8N4M6P2R9T5V0X3YC0",
  install: "uv tool install ai-stp-cli",
  ts: "2026-08-05",
};

function shell({ id, title, route, active, signedIn, body }) {
  const catalogActive = ["catalog", "component", "setup", "component-preview", "setup-preview"].includes(active);
  const nav = (href, label, on) =>
    `<a href="${href}" class="${on ? "is-active" : ""}">${label}</a>`;
  const accountNav = signedIn
    ? nav("account.html", "Аккаунт", ["account", "profile", "privacy"].includes(active)) +
      nav("devices.html", "Устройства", active === "devices")
    : "";
  const authBtn = signedIn
    ? `<a class="btn btn-outline btn-sm" href="login.html">Выйти</a>`
    : `<a class="btn btn-outline btn-sm" href="login.html">Войти</a>`;

  return `<!doctype html>
<html lang="ru" data-mode="machine">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title} · ai_stp</title>
  <link rel="stylesheet" href="../shared/tokens.css" />
  <link rel="stylesheet" href="../shared/ui.css" />
</head>
<body>
  <div class="shell" data-od-id="${id}">
    <header class="topbar" data-od-id="site-header">
      <nav class="nav" aria-label="Основная навигация">
        <a href="landing.html" class="brand"><span class="brand-mark" aria-hidden="true"></span>ai_stp</a>
        ${nav("catalog.html", "Каталог", catalogActive)}
        ${accountNav}
      </nav>
      <div class="top-actions">
        <span class="mono muted" style="font-size:11px">ru</span>
        <button type="button" class="btn btn-outline btn-sm" data-action="theme" data-od-id="theme-toggle" aria-label="Сменить тему">
          <span data-theme-label>Тёмная</span>
        </button>
        ${authBtn}
      </div>
    </header>
    <main class="main" id="main-content">
${body}
    </main>
    <footer class="footer" data-od-id="site-footer">
      <div class="row" style="justify-content:center;gap:12px">
        <div>ai_stp · setup passports</div>
        <button type="button" class="btn btn-outline btn-sm" data-action="mode" data-od-id="mode-toggle">режим · <span data-mode-label>machine</span></button>
      </div>
      <div class="footer-links">
        <a href="docs.html">Документация</a>
        <a href="legal-privacy.html">Privacy</a>
        <a href="legal-cookies.html">Cookies</a>
        <a href="legal-service-rules.html">Service rules</a>
        <a href="legal-licensing.html">Licensing</a>
        <a href="../branding.html">Брендинг</a>
        <a href="../index.html">Все экраны</a>
      </div>
    </footer>
  </div>
  <div class="proto-note">prototype · ${route}</div>
  <script src="../shared/shell.js"></script>
</body>
</html>
`;
}

const chip = (t, k = "") => `<span class="chip ${k}">${t}</span>`;
const card = (item, kind) => {
  const href = kind === "component" ? "component.html" : "setup.html";
  const label = kind === "component" ? `Компонент · ${item.type}` : "Сетап";
  return `<article class="card">
  <div class="row" style="justify-content:space-between;align-items:flex-start">
    <div class="stack-sm" style="gap:4px;min-width:0">
      <div class="mono muted" style="font-size:11px;letter-spacing:.06em;text-transform:uppercase">${label}</div>
      <h3><a href="${href}">${item.name}</a></h3>
    </div>
    <div class="row" style="gap:6px">${chip(item.trust, "chip-soft")}${chip(item.harness)}</div>
  </div>
  <p>${item.desc}</p>
  <dl class="card-meta">
    <div><dt>Версия</dt><dd>${item.version}</dd></div>
    <div><dt>Lifecycle</dt><dd>${item.lifecycle}</dd></div>
    <div style="grid-column:1/-1"><dt>Издатель</dt><dd>${item.ownerName}</dd></div>
  </dl>
  <div class="row">${item.tags.map((t) => chip(t)).join("")}</div>
</article>`;
};

const COMPONENTS = [
  { id: FIX.hook, name: "firstparty-audit-hook", desc: "Audit lifecycle hook for Claude Code sessions.", type: "hook", harness: "claude-code", version: "1.0", tags: ["security", "devops"], trust: "experimental", lifecycle: "published", verified: false, owner: FIX.account, ownerName: "ai_stp First Party", projection: "native_files", published: FIX.ts },
  { id: FIX.skill, name: "northwind-refactor-skill", desc: "Python refactor skill for Codex harness.", type: "skill", harness: "codex", version: "1.0", tags: ["python", "refactor"], trust: "experimental", lifecycle: "published", verified: false, owner: FIX.northwind, ownerName: "Northwind Labs", projection: "native_files", published: "2026-08-06" },
  { id: "component_01JQZK7B8N4M6P2R9T5V0X3YBC", name: "river-docs-mcp", desc: "Documentation MCP server for the Pi harness.", type: "mcp", harness: "pi", version: "1.0", tags: ["documentation"], trust: "experimental", lifecycle: "published", verified: false, owner: "account_01JQZK7B8N4M6P2R9T5V0X3YA1", ownerName: "River Guild", projection: "package", published: FIX.ts },
];
const SETUPS = [
  { id: FIX.setup, name: "claude-code first-party setup", desc: "Pinned first-party composition for Claude Code harness.", harness: "claude-code", version: "1.0", purpose: "baseline-dev", role: "developer", tags: ["security", "devops"], trust: "experimental", lifecycle: "published", verified: false, owner: FIX.account, ownerName: "ai_stp First Party", published: FIX.ts, components: [FIX.hook] },
  { id: "setup_01JQZK7B8N4M6P2R9T5V0X3YC1", name: "codex northwind setup", desc: "Codex-focused composition from Northwind Labs.", harness: "codex", version: "1.0", purpose: "refactor", role: "developer", tags: ["python", "refactor"], trust: "experimental", lifecycle: "published", verified: false, owner: FIX.northwind, ownerName: "Northwind Labs", published: "2026-08-06", components: [FIX.skill] },
];

function installBlock(cmd) {
  return `<section class="panel stack-sm">
  <h2>Использовать через CLI</h2>
  <p class="muted" style="margin:0;font-size:14px">Команда использует стабильный идентификатор и версию объекта.</p>
  <div class="row" style="align-items:stretch">
    <code class="codebox" style="flex:1">${cmd}</code>
    <button type="button" class="btn btn-secondary" data-action="copy" data-copy="${cmd}">Copy</button>
  </div>
  <a href="docs.html" class="muted" style="font-size:13px;text-decoration:underline">Документация по CLI</a>
</section>`;
}

function objectPage(item, kind, preview) {
  const isC = kind === "component";
  const back = preview
    ? `<a class="back" href="${isC ? "component-edit.html" : "setup-edit.html"}">← Назад к редактированию</a>`
    : `<a class="back" href="catalog.html">← Назад в каталог</a>`;
  const banner = preview
    ? `<div class="banner"><span>Черновик / не опубликовано · видите только вы</span><a class="btn btn-outline btn-sm" href="${isC ? "component-edit.html" : "setup-edit.html"}">Редактировать</a></div>`
    : "";
  const details = isC
    ? [["Версия", item.version, "mono"], ["Lifecycle", item.lifecycle], ["Харнесс", item.harness], ["Тип", item.type], ["Проекция", item.projection, "mono"], ["Опубликовано", item.published, "mono"]]
    : [["Назначение", item.purpose], ["Целевая роль", item.role], ["Версия", item.version, "mono"], ["Харнесс", item.harness], ["Lifecycle", item.lifecycle], ["Опубликовано", item.published, "mono"]];
  const extra = isC
    ? `<section class="stack-sm"><h2>Совместимость</h2><dl class="dl"><div><dt>Учётные данные</dt><dd>Не требуются</dd></div><div><dt>Лицензия</dt><dd class="mono">Apache-2.0</dd></div></dl></section>`
    : `<section class="stack-sm"><h2>Закреплённые компоненты</h2>${item.components.map((id) => `<div class="list-item"><a href="component.html" class="mono" style="text-decoration:underline">${id}</a><span class="muted">Версия 1.0</span></div>`).join("")}</section>`;
  return `<article class="stack">
  ${back}
  ${banner}
  <div class="stack-sm">
    <h1>${item.name}</h1>
    <p class="lede" style="font-size:15px">${item.desc}</p>
    <div class="row">${chip(item.trust, "chip-soft")}${chip(item.harness)}${!preview ? `<a class="btn btn-outline btn-sm" href="${isC ? "component-edit.html" : "setup-edit.html"}">Редактировать</a>` : ""}</div>
  </div>
  <dl class="dl">
    ${details.map((d) => `<div><dt>${d[0]}</dt><dd class="${d[2] || ""}">${d[1]}</dd></div>`).join("")}
    <div><dt>Verified</dt><dd>${item.verified ? "Да" : "Нет"}</dd></div>
    <div><dt>Trust line</dt><dd>${item.trust}</dd></div>
    <div class="span-2"><dt>Издатель</dt><dd><a href="publisher.html" class="mono" style="text-decoration:underline">${item.owner}</a> · ${item.ownerName}</dd></div>
    <div class="span-2"><dt>Теги</dt><dd class="row">${item.tags.map((t) => chip(t)).join("")}</dd></div>
  </dl>
  <section class="object-description stack-sm">
    <div class="row" style="justify-content:space-between"><h2>Описание</h2><div class="version-note"><span class="mono">v${item.version}</span></div></div>
    <div class="markdown">
      <h3>Назначение</h3>
      <p>${item.desc} Версия сохраняет паспорт объекта и совместимость с <a href="docs.html">публичным контрактом</a>.</p>
      <pre>${isC ? "ai-stp component inspect " + item.id : "ai-stp setup show " + item.id}</pre>
    </div>
  </section>
  ${extra}
  ${installBlock(`ai-stp use ${item.id}@${item.version}`)}
  <p class="mono muted" style="font-size:11px;margin:0">route: /catalog/${isC ? "components" : "setups"}/[stableId]</p>
</article>`;
}

function editPage(kind) {
  const item = kind === "component" ? COMPONENTS[0] : SETUPS[0];
  return `<div class="mid stack">
  <a class="back" href="account.html">← Рабочая область</a>
  <div class="row" style="justify-content:space-between">
    <div>
      <h1>Редактирование версии</h1>
      <p class="lede" style="font-size:14px">Паспорт версии редактируется в CLI; веб показывает статус и предпросмотр.</p>
    </div>
    <a class="btn btn-outline" href="${kind}-preview.html">Предпросмотр версии</a>
  </div>
  <div class="panel stack-sm">
    <strong style="font-weight:500">${item.name}</strong>
    <span class="mono muted" style="font-size:12px">${item.id}</span>
    <p class="muted" style="margin:0;font-size:14px">Состав ${kind === "setup" ? "сетапа" : "компонента"} не редактируется в веб-интерфейсе.</p>
    <div class="row">
      <code class="codebox" style="flex:1">ai-stp ${kind} sync ${item.id}</code>
      <button class="btn btn-secondary" data-action="copy" data-copy="ai-stp ${kind} sync ${item.id}">Copy</button>
    </div>
  </div>
</div>`;
}

function legal(kind, title, blurb) {
  return `<article class="legal stack">
  <a class="back" href="landing.html">← На главную</a>
  <div>
    <h1>${title}</h1>
    <div class="legal-meta"><span>Версия 1.0</span><span>Вступает в силу 05.08.2026</span><span>Русский</span></div>
  </div>
  <div class="markdown">
    <h3>Содержание</h3>
    <ol><li>Назначение</li><li>Обработка данных</li><li>Контакты</li></ol>
    <h3>Назначение</h3>
    <p>${blurb}</p>
    <p>Текст страницы является спокойной публичной справкой.</p>
    <h3>Обработка данных</h3>
    <p>Сведения об аккаунте используются для предоставления доступа к объектам и устройствам.</p>
  </div>
</article>`;
}

const pages = {
  "landing.html": {
    id: "page-landing", title: "Главная", route: "/", active: "landing", signedIn: false,
    body: `<div class="stack">
  <section class="stack-sm" style="gap:16px">
    <h1>Один сетап для каждого coding-харнесса</h1>
    <p class="lede" style="display:inline-flex;align-items:center;gap:10px;max-width:none">
      <span class="brand-mark" aria-hidden="true" style="height:16px"></span>
      <span class="row" style="gap:8px;align-items:baseline">
        <span style="color:var(--fg);font-weight:500">ai_stp</span>
        <span class="mono muted" style="font-size:12px;letter-spacing:0.04em">hand to hand harness ai setup</span>
      </span>
    </p>
    <div class="row">
      <a class="btn btn-primary" href="catalog.html">Открыть каталог</a>
      <a class="btn btn-outline" href="login.html">Войти</a>
    </div>
  </section>
  ${installBlock(FIX.install)}
</div>`,
  },
  "login.html": {
    id: "page-login", title: "Вход", route: "/login", active: "login", signedIn: false,
    body: `<div class="narrow stack">
  <div><h1>Вход</h1><p class="lede" style="font-size:14px">Войдите через поддерживаемого провайдера. Сессия хранится в защищённой HttpOnly cookie.</p></div>
  <div class="stack-sm">
    <a class="btn btn-primary btn-block" href="account.html">Войти через Google</a>
    <a class="btn btn-secondary btn-block" href="account.html">Войти через GitHub</a>
  </div>
</div>`,
  },
  "catalog.html": {
    id: "page-catalog", title: "Каталог", route: "/catalog", active: "catalog", signedIn: false,
    body: `<div class="stack">
  <div><h1>Каталог</h1><p class="lede" style="font-size:14px">Компоненты и полные сетапы из опубликованного каталога.</p></div>
  <section class="stack-sm">
    <div class="search-row">
      <div class="field"><label for="q">Поиск</label><input id="q" placeholder="Поиск компонентов и сетапов" /></div>
      <button class="btn btn-outline" type="button">Фильтры</button>
    </div>
    <div class="row">
      <div class="seg" role="group"><button class="is-on" type="button">Компоненты</button><button type="button">Сетапы</button></div>
      <span class="mono muted" style="font-size:12px">${COMPONENTS.length}</span>
    </div>
  </section>
  <section class="stack-sm"><h2 style="margin:0">Компоненты</h2><div class="grid-3">${COMPONENTS.map((x) => card(x, "component")).join("")}</div></section>
  <section class="stack-sm"><h2 style="margin:0">Сетапы</h2><div class="grid-2">${SETUPS.map((x) => card(x, "setup")).join("")}</div></section>
</div>`,
  },
  "component.html": { id: "page-component", title: "Компонент", route: "/catalog/components/[id]", active: "component", signedIn: false, body: objectPage(COMPONENTS[1], "component", false) },
  "setup.html": { id: "page-setup", title: "Сетап", route: "/catalog/setups/[id]", active: "setup", signedIn: false, body: objectPage(SETUPS[0], "setup", false) },
  "component-preview.html": { id: "page-component-preview", title: "Preview компонента", route: "component preview", active: "component-preview", signedIn: true, body: objectPage(COMPONENTS[0], "component", true) },
  "setup-preview.html": { id: "page-setup-preview", title: "Preview сетапа", route: "setup preview", active: "setup-preview", signedIn: true, body: objectPage(SETUPS[0], "setup", true) },
  "component-edit.html": { id: "page-component-edit", title: "Edit компонента", route: "component edit", active: "component-edit", signedIn: true, body: editPage("component") },
  "setup-edit.html": { id: "page-setup-edit", title: "Edit сетапа", route: "setup edit", active: "setup-edit", signedIn: true, body: editPage("setup") },
  "publisher.html": {
    id: "page-publisher", title: "Издатель", route: "/publishers/[account]", active: "publisher", signedIn: false,
    body: `<article class="stack">
  <a class="back" href="catalog.html">← Назад в каталог</a>
  <section class="profile-head">
    <div class="avatar">NL</div>
    <div class="stack-sm" style="gap:8px;min-width:0">
      <div class="row"><h1 style="margin:0">Northwind Labs</h1>${chip("verified", "chip-ok")}</div>
      <p class="muted" style="margin:0;max-width:62ch">Codex-focused tooling publisher: review skills, MCP bridges, session hooks.</p>
      <div class="row"><a href="https://github.com/northwind" class="muted" style="text-decoration:underline;font-size:14px">GitHub</a></div>
    </div>
  </section>
  <section class="stack-sm"><h2>Компоненты</h2><div class="grid-2">${COMPONENTS.filter((x) => x.owner === FIX.northwind).map((x) => card(x, "component")).join("")}</div></section>
  <section class="stack-sm"><h2>Сетапы</h2><div class="grid-2">${SETUPS.filter((x) => x.owner === FIX.northwind).map((x) => card(x, "setup")).join("")}</div>
  <p class="mono muted" style="font-size:11px;margin:0">route: /publishers/[account]</p></section>
</article>`,
  },
  "account.html": {
    id: "page-account", title: "Аккаунт", route: "/account", active: "account", signedIn: true,
    body: `<div class="stack">
  <div class="row" style="justify-content:space-between">
    <div><h1>Аккаунт</h1><p class="mono muted" style="font-size:12px;margin:6px 0 0">${FIX.account}</p></div>
    <div class="row">
      <a class="btn btn-outline btn-sm" href="publisher.html">Публичная страница</a>
      <a class="btn btn-outline btn-sm" href="profile-preview.html">Предпросмотр</a>
      <a class="btn btn-outline btn-sm" href="profile.html">Редактировать</a>
    </div>
  </div>
  <section class="stack-sm">
    <div class="row" style="justify-content:space-between"><h2>Мои объекты</h2><a class="back" href="account-empty.html">Пустое состояние</a></div>
    <div class="grid-2">
      ${COMPONENTS.filter((x) => x.owner === FIX.account).map((x) => card(x, "component")).join("")}
      ${SETUPS.filter((x) => x.owner === FIX.account).map((x) => card(x, "setup")).join("")}
    </div>
  </section>
  <section class="stack-sm">
    <h2>Привязанные идентичности</h2>
    <div class="list-item"><div class="row">${chip("google", "chip-soft")}<span class="mono muted" style="font-size:12px">${FIX.ts}</span></div><button class="btn btn-outline btn-sm" disabled>Отвязать</button></div>
  </section>
  <div class="row">
    <a class="btn btn-outline btn-sm" href="privacy.html">Приватность</a>
    <a class="btn btn-outline btn-sm" href="devices.html">Устройства</a>
    <a class="btn btn-outline btn-sm" href="component-edit.html">Edit component</a>
    <a class="btn btn-outline btn-sm" href="setup-edit.html">Edit setup</a>
  </div>
</div>`,
  },
  "account-empty.html": {
    id: "page-account-empty", title: "Аккаунт · empty", route: "/account empty", active: "account", signedIn: true,
    body: `<div class="stack">
  <div class="row" style="justify-content:space-between">
    <div><h1>Аккаунт</h1><p class="mono muted" style="font-size:12px;margin:6px 0 0">${FIX.account}</p></div>
    <a class="btn btn-outline btn-sm" href="account.html">Показать объекты</a>
  </div>
  <section class="panel stack-sm">
    <h2>Пока нет опубликованных объектов</h2>
    <p class="muted" style="margin:0;font-size:14px">Компонент или сетап создаётся и синхронизируется через CLI.</p>
    <div class="row">
      <code class="codebox" style="flex:1">ai-stp component sync ./my-component</code>
      <button class="btn btn-secondary" data-action="copy" data-copy="ai-stp component sync ./my-component">Copy</button>
    </div>
    <a href="docs.html" class="muted" style="font-size:13px;text-decoration:underline">Документация по CLI</a>
  </section>
</div>`,
  },
  "profile.html": {
    id: "page-profile", title: "Профиль", route: "/account/profile", active: "profile", signedIn: true,
    body: `<div class="mid stack">
  <a class="back" href="account.html">← Аккаунт</a>
  <div class="row" style="justify-content:space-between">
    <div><h1>Публичный профиль</h1><div class="row"><span class="chip chip-ok">published</span></div></div>
    <a class="btn btn-outline" href="profile-preview.html">Предпросмотр</a>
  </div>
  <section class="stack-sm">
    <div class="profile-head">
      <div class="avatar">AS</div>
      <div class="row">
        <button class="btn btn-outline btn-sm" type="button">Загрузить файл</button>
        <button class="btn btn-outline btn-sm" type="button">GitHub</button>
        <button class="btn btn-outline btn-sm" type="button">Google</button>
        <button class="btn btn-outline btn-sm" type="button">Удалить</button>
      </div>
    </div>
    <label class="field"><span>Display name</span><input value="ai_stp First Party" /></label>
    <label class="field"><span>Короткое bio</span><textarea>Platform first-party publisher for launch corpus and fixture parity.</textarea><span class="muted" style="font-size:12px">Plain text · 68/180</span></label>
    <div class="stack-sm">
      <div class="row" style="justify-content:space-between"><strong style="font-weight:500">Ссылки</strong><button class="btn btn-outline btn-sm" type="button">Добавить</button></div>
      <div class="link-row">
        <span class="drag">⋮⋮</span>
        <label class="field"><span>Label</span><input value="GitHub" /></label>
        <label class="field"><span>URL</span><input value="https://github.com/ai-stp" /></label>
        <button class="btn btn-outline btn-sm" type="button">Удалить</button>
      </div>
    </div>
  </section>
  <div class="sticky-actions">
    <span class="mono muted" style="font-size:11px">Все изменения сохранены</span>
    <div class="row">
      <button class="btn btn-secondary" type="button">Сохранить черновик</button>
      <button class="btn btn-primary" type="button">Опубликовать</button>
    </div>
  </div>
</div>`,
  },
  "profile-preview.html": {
    id: "page-profile-preview", title: "Preview профиля", route: "/account/profile/preview", active: "profile", signedIn: true,
    body: `<article class="stack">
  <a class="back" href="profile.html">← К редактированию</a>
  <div class="banner"><span>Предпросмотр — видите только вы</span><a class="btn btn-outline btn-sm" href="profile.html">Редактировать</a></div>
  <section class="profile-head">
    <div class="avatar">AS</div>
    <div class="stack-sm" style="gap:8px;min-width:0">
      <div class="row"><h1 style="margin:0">ai_stp First Party</h1>${chip("verified", "chip-ok")}</div>
      <p class="muted" style="margin:0;max-width:62ch">Platform first-party publisher for launch corpus and fixture parity.</p>
      <div class="row"><a href="https://github.com/ai-stp" class="muted" style="text-decoration:underline;font-size:14px">GitHub</a></div>
    </div>
  </section>
  <section class="stack-sm"><h2>Компоненты</h2><div class="grid-2">${COMPONENTS.filter((x) => x.owner === FIX.account).map((x) => card(x, "component")).join("")}</div></section>
  <section class="stack-sm"><h2>Сетапы</h2><div class="grid-2">${SETUPS.filter((x) => x.owner === FIX.account).map((x) => card(x, "setup")).join("")}</div></section>
</article>`,
  },
  "privacy.html": {
    id: "page-privacy", title: "Приватность", route: "/account/privacy", active: "privacy", signedIn: true,
    body: `<div class="stack"><a class="back" href="account.html">← Аккаунт</a><h1>Приватность</h1><div class="panel panel-empty">Настройки приватности ограничены данными привязанных идентичностей.</div></div>`,
  },
  "devices.html": {
    id: "page-devices", title: "Устройства", route: "/devices", active: "devices", signedIn: true,
    body: `<div class="stack">
  <h1>Устройства</h1>
  <div class="card">
    <div class="row" style="justify-content:space-between">
      <div><strong style="font-weight:500">fixture-device</strong><div class="mono muted" style="font-size:12px;margin-top:4px">device_01JQZK7B8N4M6P2R9T5V0X3Y7Z</div></div>
      ${chip("active · current", "chip-ok")}
    </div>
    <dl class="card-meta"><div><dt>ОС</dt><dd>linux</dd></div><div><dt>Harness</dt><dd>claude-code 2.1.0</dd></div></dl>
  </div>
</div>`,
  },
  "docs.html": {
    id: "page-docs", title: "Документация", route: "/docs", active: "docs", signedIn: false,
    body: `<div class="docs-layout">
  <aside class="docs-nav" aria-label="Разделы">
    <button class="is-on" type="button">Начало работы</button>
    <button type="button">Каталог</button>
    <button type="button">Публикация</button>
    <button type="button">CLI</button>
  </aside>
  <section class="stack-sm">
    <div class="row" style="justify-content:space-between">
      <span class="mono muted" style="font-size:11px">docs / getting-started</span>
      <div class="row">
        <select class="select-compact"><option>v1.0</option></select>
        <select class="select-compact"><option>Русский</option><option>English</option></select>
      </div>
    </div>
    <article class="markdown">
      <h1>Начало работы</h1>
      <p>Установите CLI, авторизуйте устройство и синхронизируйте первый объект.</p>
      <h3>Быстрый путь</h3>
      <ol><li>Установите <code>ai-stp-cli</code>.</li><li>Проверьте сессию.</li><li>Синхронизируйте объект.</li></ol>
      <pre>ai-stp login
ai-stp catalog search --harness codex
ai-stp setup use setup_…@1.0</pre>
      <p>См. <a href="catalog.html">каталог</a>.</p>
    </article>
  </section>
</div>`,
  },
  "legal-privacy.html": { id: "page-legal-privacy", title: "Privacy", route: "/legal/privacy", active: "legal", signedIn: false, body: legal("privacy", "Privacy", "Как обрабатываются данные аккаунта и устройства.") },
  "legal-cookies.html": { id: "page-legal-cookies", title: "Cookies", route: "/legal/cookies", active: "legal", signedIn: false, body: legal("cookies", "Cookies", "Какие cookies поддерживают вход и безопасность сессии.") },
  "legal-service-rules.html": { id: "page-legal-service-rules", title: "Service rules", route: "/legal/service-rules", active: "legal", signedIn: false, body: legal("service-rules", "Service rules", "Правила использования публичного каталога и CLI.") },
  "legal-licensing.html": { id: "page-legal-licensing", title: "Licensing", route: "/legal/licensing", active: "legal", signedIn: false, body: legal("licensing", "Licensing / author content responsibility", "Автор отвечает за права на публикуемый контент и указание лицензии.") },
  "not-found.html": {
    id: "page-error-404", title: "404", route: "404", active: "error", signedIn: false,
    body: `<section class="error-page">
  <span class="mono muted" style="font-size:12px">HTTP 404</span>
  <h1>Страница не найдена</h1>
  <p class="lede" style="font-size:15px">Возможно, адрес устарел или объект больше не доступен.</p>
  <div class="row"><a class="btn btn-primary" href="catalog.html">В каталог</a><a class="btn btn-outline" href="landing.html">На главную</a></div>
</section>`,
  },
  "error-500.html": {
    id: "page-error-500", title: "500", route: "500", active: "error", signedIn: false,
    body: `<section class="error-page">
  <span class="mono muted" style="font-size:12px">HTTP 500</span>
  <h1>Что-то пошло не так</h1>
  <p class="lede" style="font-size:15px">Попробуйте повторить действие.</p>
  <span class="mono muted" style="font-size:12px">request id: req_01JQZK7B8N4M6P2R9T5V0X3Y7Z</span>
  <div class="row"><a class="btn btn-primary" href="error-500.html">Попробовать снова</a><a class="btn btn-outline" href="landing.html">На главную</a></div>
</section>`,
  },
};

const shellJs = `/* ai_stp multi-page prototype shell: theme/mode + copy */
(function () {
  var KEY = "ai_stp_proto_mode";
  function applyMode(mode) {
    document.documentElement.setAttribute("data-mode", mode);
    localStorage.setItem(KEY, mode);
    document.querySelectorAll("[data-mode-label]").forEach(function (el) { el.textContent = mode; });
    var isMachine = mode === "machine";
    document.querySelectorAll("[data-theme-label]").forEach(function (el) {
      el.textContent = isMachine ? "Тёмная" : "Светлая";
    });
  }
  applyMode(localStorage.getItem(KEY) || "machine");
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-action]");
    if (!t) return;
    var a = t.getAttribute("data-action");
    if (a === "theme" || a === "mode") {
      applyMode((localStorage.getItem(KEY) || "machine") === "machine" ? "human" : "machine");
    } else if (a === "copy") {
      var v = t.getAttribute("data-copy") || "";
      var prev = t.textContent;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(v).then(function () {
          t.textContent = "Скопировано";
          setTimeout(function () { t.textContent = prev; }, 1400);
        }).catch(function () {
          t.textContent = "Ошибка";
          setTimeout(function () { t.textContent = prev; }, 1400);
        });
      }
    }
  });
})();
`;
fs.writeFileSync(path.join(SHARED, "shell.js"), shellJs, "utf8");

Object.entries(pages).forEach(([file, meta]) => {
  fs.writeFileSync(path.join(PAGES, file), shell(meta), "utf8");
});

const indexRows = Object.entries(pages)
  .map(
    ([file, meta]) =>
      `    <div class="card">\n      <a href="./pages/${file}">${meta.title}</a>\n      <div class="mono">${meta.route} · pages/${file}</div>\n    </div>`
  )
  .join("\n");

const indexHtml = `<!doctype html>
<html lang="ru" data-mode="machine">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ai_stp · HTML prototypes index</title>
  <link rel="stylesheet" href="./shared/tokens.css" />
  <link rel="stylesheet" href="./shared/ui.css" />
  <style>
    body { margin:0; min-height:100vh; font-family:var(--font-sans); background:var(--bg); color:var(--fg); padding:48px 24px; }
    .wrap { max-width:800px; margin:0 auto; }
    h1 { font-size:28px; font-weight:500; letter-spacing:-0.02em; margin:0 0 8px; }
    .intro { color:var(--muted); margin:0 0 28px; line-height:1.5; }
    .section-title { font-family:var(--font-mono); font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:var(--muted); margin:28px 0 12px; }
    .card { border:1px solid var(--border); background:var(--surface); border-radius:8px; padding:14px 16px; margin-bottom:10px; }
    .card a { color:var(--fg); font-weight:500; text-decoration:none; }
    .card a:hover { color:var(--accent); }
    .mono { font-family:var(--font-mono); font-size:11px; color:var(--muted); margin-top:6px; }
    .row-actions { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; }
    .badge { display:inline-block; font-family:var(--font-mono); font-size:10px; letter-spacing:0.04em; text-transform:uppercase; color:var(--accent); border:1px solid var(--accent); border-radius:4px; padding:2px 6px; margin-left:8px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>ai_stp · HTML prototypes</h1>
    <p class="intro">Одна HTML-страница = один экран. Shared assets в <span class="mono" style="color:var(--fg)">shared/</span>. Routes 1:1 с apps/web.</p>
    <div class="row-actions">
      <a class="btn btn-primary" href="./pages/landing.html">Landing</a>
      <a class="btn btn-outline" href="./branding.html">Брендинг</a>
      <button type="button" class="btn btn-outline btn-sm" data-action="theme"><span data-theme-label>Тёмная</span></button>
    </div>
    <div class="card" style="border-color:var(--accent)">
      <a href="./branding.html">Брендинг / design tokens</a><span class="badge">brand</span>
      <div class="mono">branding.html · mark, color, type, rules, voice</div>
    </div>
    <p class="section-title">Product screens (${Object.keys(pages).length})</p>
${indexRows}
    <p class="section-title">Structure</p>
    <div class="card">
      <div class="mono" style="margin:0;line-height:1.8;white-space:pre">prototypes/
  index.html
  branding.html
  pages/*.html
  shared/{tokens.css, ui.css, shell.js, fonts/}</div>
    </div>
  </div>
  <script src="./shared/shell.js"></script>
</body>
</html>
`;
fs.writeFileSync(path.join(ROOT, "index.html"), indexHtml, "utf8");
console.log("OK", Object.keys(pages).length, "pages + index");
