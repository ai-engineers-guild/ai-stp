---
description: "Сборка, проверка и откат deploy-профилей web."
last_verified: "2026-08-16"
---

# Deploy-профили web

Канонический контракт принадлежит `SPEC-038`, архитектурный выбор — `ADR-0080`.
Profiles являются build-time конфигурацией точного standalone artifact, а не
runtime feature service.

Профиль `public_saas` является default-профилем сборки сайта. Это закреплено в
`apps/web/config/features.yaml`, в dev Compose и в рецепте `just web-build`; production
Dockerfile и production Compose также явно используют `public_saas`. Профиль
`self_hosted` включается только явным `AI_STP_WEB_PROFILE=self_hosted` override.

## Profiles

- `public_saas` — публичный SaaS: content hub, contact и правовые страницы включены;
- `self_hosted` — коробочная поставка: каталог, документация и account surface без
  SaaS-материалов, contact и публичных policy pages.

Полный набор значений хранится в `apps/web/config/features.yaml`. Новый key нельзя
добавлять без owner, issue, consumer и теста.

## Локальная проверка

```bash
cd apps/web
# Default site artifact: public SaaS.
AI_STP_WEB_PROFILE=public_saas bun run build
AI_STP_WEB_PROFILE=self_hosted bun run build
bun run test:feature-profiles
```

Build override принимает только точные `true`/`false`:

```bash
AI_STP_FEATURE_CONTENT_HUB=false bun run build
AI_STP_FEATURE_SAAS_PUBLIC_PAGES=false bun run build
AI_STP_FEATURE_CATALOG_USAGE_METRICS=true bun run build
```

Оба профиля оставляют `catalog_usage_metrics` выключенным. Override не открывает
серверную запись counters и не заменяет attribution/terms gate `SPEC-050`.

После смены profile dev server перезапускается полностью. Значение, изменённое только
в runtime environment уже собранного image, не меняет artifact.

## Проверка результата

Для `public_saas` human и machine content/contact/legal routes, `/feed.xml`, navigation,
sitemap и `llms.txt` содержат SaaS-поверхности. Для `self_hosted` эти route деревья и
feed отвечают 404, а ссылки и discovery entries отсутствуют. Выключенная human-поверхность
и её machine pair обе отвечают 404. Команда `test:feature-profiles` последовательно
собирает оба профиля без Docker и проверяет standalone server на `127.0.0.1:3100`
через Playwright. Unit inventory gate сверяет каждый human `page.tsx` с machine
registry (`SPEC-036`).

## Откат

Откат выполняется развёртыванием предыдущего точного image либо новой сборкой
`self_hosted`. Не менять profile внутри уже собранного контейнера и не подменять static
assets от другого build.
