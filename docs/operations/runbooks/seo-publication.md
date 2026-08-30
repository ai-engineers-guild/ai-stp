---
description: "Runbook: серверные SEO-ревизии, sitemap и необязательное LiteLLM enrichment."
last_verified: "2026-08-29"
---

# SEO publication

## Когда применять

После публикации компонента или сетапа, импорта статей, изменения сервиса
или страны страница должна получить активную base SEO-ревизию без модели.
Обогащение через LiteLLM включается отдельно и не блокирует публикацию.

## Проверить

1. Worker обработал `seo_build` и указатель `seo_active_revision` ссылается
   на `state=active`.
2. `GET /v1/seo/subjects/{kind}/{id}?locale=en` отдаёт профиль с
   `Cache-Control: public`.
3. `/sitemap.xml` и `/sitemaps/{kind}-{locale}-{page}.xml` содержат только
   `index_eligible` URL.
4. `/llms.txt` остаётся компактным и ссылается на `/llms/catalog.ndjson`.
5. `/og/{revision_id}.png` отвечает 1200×630 с `immutable` cache.

## Enrichment

Профиль compose `seo_enrichment` поднимает LiteLLM (`seo-writer`) и CLIPROXY
(официальный образ `eceasy/cli-proxy-api`) в одной сети `internal`. LiteLLM
ходит в `http://cliproxy:8317/v1`. Порт 8317 на хост не публикуется. Worker
читает только `AI_STP_SEO_ENRICHMENT_URL`, credential процесса и alias;
`AI_STP_CLIPROXY_*` попадают только в контейнер LiteLLM.

Переносимая сессия — JSON в `deploy/cliproxy/auths/` (это `auth-dir`
CLIProxyAPI, внутри контейнера `/root/.cli-proxy-api`). Это не вход `agy` и
не `~/.gemini`. Файлы `antigravity-*.json` копируются между машинами; CLIPROXY
подхватывает каталог без перезапуска (hot reload).

Локально, если CLIPROXY уже логинился на этой машине:

```sh
cp "$HOME/.cli-proxy-api"/antigravity*.json deploy/cliproxy/auths/
```

На Windows PowerShell:

```powershell
Copy-Item "$env:USERPROFILE\.cli-proxy-api\antigravity*.json" deploy\cliproxy\auths\
```

На сервер уходит тот же каталог, не cookie браузера:

```sh
scp -r deploy/cliproxy/auths/ user@server:ai_stp/deploy/cliproxy/auths/
```

Первый вход или просроченный refresh — логин внутри контейнера. Callback
Antigravity слушает `127.0.0.1:51121`.

```sh
docker compose -f docker-compose.dev.yml \
  -f docker-compose.seo-enrichment.yml --profile seo_enrichment \
  exec cliproxy /CLIProxyAPI/CLIProxyAPI -no-browser -antigravity-login
```

На сервере без браузера сначала туннель с рабочей машины
(`ssh -L 51121:127.0.0.1:51121 user@server`), затем та же команда `exec`.
Google вернёт код на `localhost:51121`, SSH донесёт его до контейнера.
Не открывайте 8317 и 51121 в интернет.

```sh
docker compose -f docker-compose.dev.yml \
  -f docker-compose.seo-enrichment.yml --profile seo_enrichment up -d
docker compose -f docker-compose.dev.yml \
  -f docker-compose.seo-enrichment.yml --profile seo_enrichment \
  exec worker python -m ai_stp_platform.seo.enqueue_pending
```

Команда сначала ставит `seo_build` для профилей со старой версией шаблона,
а уже актуальные профили отправляет в `seo_enrich`. После сборки worker сам
поставит обогащение. Канонический origin сервер берёт из
`AI_STP_SEO_PUBLIC_ORIGIN`, а при его отсутствии — из `NEXT_PUBLIC_APP_URL`;
на production это должен быть внешний HTTPS URL сайта, не адрес из запроса.

`enqueue_pending` не переставит job, который уже `dead_letter` с тем же
idempotency key: такие задания retry/reset отдельно, после живого CLIPROXY.

Worker отклоняет водяной или неполный ответ до публикации и делает до пяти
попыток исправления с безопасной причиной отказа. Если все попытки не прошли
quality gate, активной остаётся детерминированная base revision.

Выключение флага оставляет base-ревизию активной. Откат:
`POST /v1/seo/subjects/{kind}/{id}/rollback`.

## Откат схемы

Таблицы additive. Downgrade `0031_seo_projections` удаляет SEO-таблицы и
nullable поля `external_product.description`/`source_url`. Web при отсутствии
active revision использует текущий presenter и `noindex`.
