---
description: "SPEC-049: On-demand GitHub metadata, CLI-only blast radius и честный context budget в Web."
last_verified: "2026-08-16"
---

# SPEC-049: On-demand GitHub metadata and Web context budget

## Цель

Упростить карточку точной версии: звёзды GitHub и признак архива читаются один
раз при открытии exact detail, значок архива появляется только для реально
архивного repository, blast radius остаётся локальной CLI-операцией, а Web
показывает воспроизводимую оценку опубликованного setup без имитации локального
расхода модели. Локальная dev-сборка обслуживает browser-facing `/v1` media без Caddy.

## Границы

Входит:

- восстановление dev-only `/v1/*` proxy и avatar/media smoke на `localhost:3000`;
- один bounded on-demand GitHub metadata request для exact component/setup detail;
- совместный минимальный ответ `stars` + `archived`, без polling/history UI;
- удаление server/Web blast-radius projection при сохранении CLI contract;
- общий детерминированный estimator для CLI и server projection;
- public/owner exact setup context-budget endpoint и Web panel;
- client-only cost calculator с явно введённой ставкой;
- owner Git identity/signing policy в `AGENTS.md`.

Не входит actual model usage telemetry, внешний tokenizer/pricing API, автоматическое
изменение lifecycle, Web-доступ к локальному registry или installed targets,
production/Caddy deployment и импорт локального CLI report в Web.

Эта спецификация заменяет server/Web delivery требований `SPEC-047` `REQ-4705`…
`REQ-4712` в части periodic GitHub archive evidence и account blast radius.
Локальные смыслы `SPEC-043` и `SPEC-044` сохраняются только там, где явно не
заменены этой спецификацией.

## Термины

- **GitHub metadata** — best-effort пара `stars` и `archived`, полученная для
  repository из immutable exact-version passport при открытии detail.
- **Context budget** — детерминированная оценка потенциально загружаемого
  текстового контекста exact setup graph, а не фактический расход модели.
- **Cost estimate** — клиентская арифметика над context budget и явно введённой
  пользователем ставкой input per million.

## Требования

- `REQ-4901`: `docker-compose.dev.yml` запускает `Dockerfile.dev`/`next dev` и
  проксирует `/v1/*` к `AI_STP_API_BASE_URL` без Caddy. Avatar и component media
  доступны через Web origin; production routing при этом не дублируется в Next.

- `REQ-4902`: Detail page инициирует ровно один GitHub metadata request. API
  принимает exact catalog coordinate, сам разрешает repository из видимого
  immutable passport и обращается только к фиксированному public `api.github.com`
  endpoint с bounded timeout/size, no credentials и no redirects.

- `REQ-4903`: GitHub metadata response содержит только nullable non-negative
  `stars` и nullable boolean `archived`. `403/404/429/5xx`, timeout, malformed,
  oversized, private/unsupported source дают оба nullable поля без отказа detail.

- `REQ-4904`: GitHub metadata не запрашивается для catalog list/cards. Detail
  header показывает stars при доступном значении и компактный `Archived` badge
  рядом с GitHub link только при `archived=true`; active/unavailable/failure не
  создают badge, panel, freshness, attribution или proposal.

- `REQ-4905`: Periodic server archive polling, archive latest/history projection
  и Web evidence panel выводятся из активного пути. Старые queued derived jobs
  завершаются безопасно как superseded/no-op; удаление derived cache storage идёт
  forward migration с ограниченным rollback в пустую структуру.

- `REQ-4906`: Web и server API не предоставляют blast radius. Локальная команда
  `select blast-radius`, `BlastRadiusReport`, `authority_boundary=local_registry`
  и её tests остаются неизменными; Web может только копировать точную CLI-команду.

- `REQ-4907`: Один shared pure estimator используется CLI и server. Он проверяет
  exact graph/digests, считает `instruction` как always-loaded, `skill`, `agent`
  и `command` как conditionally-loaded, различает exact UTF-8 bytes и estimated
  Unicode codepoints/4 и не превращает unreadable/missing bytes в ноль.

- `REQ-4908`: Точная оценка контекста сетапа доступна публично только для
  публичной версии, а закрытая версия — только владельцу. Ответ содержит
  координату, estimator, always/conditional/total, число недоступных
  компонентов и разбор по компонентам, но не байты артефакта, перечень
  аккаунта, локальный выбор или установку.

- `REQ-4909`: Карточка сетапа показывает оценку контекста всем, кому видна exact
  version. Панель живёт в правом рельсе, не в левой/основной колонке, в порядке
  Author → Context budget → Use via CLI → Version history; на узком экране тот
  же document/accessible order рельса сохраняется. Свернутая поверхность держит
  только заголовок, одну фразу и потенциальный итог; разбор always/conditional,
  вклад компонентов и оценка стоимости открываются первым раскрытием. Профиль
  estimator не показывается по умолчанию. Недоступное состояние явно; интерфейс
  прямо сообщает, что это оценка потенциального контекста, а не фактический
  расход модели.

- `REQ-4910`: Cost calculator работает только в браузере по формуле
  `total * input_per_million / 1_000_000`, не сохраняет ввод и не вызывает pricing
  API. Без валидной явной ставки amount отсутствует; stale/actual price не выдумывается.

- `REQ-4911`: Personalized baseline/delta по installed/selected state остаётся
  локальным CLI `select impact`. Web не выводит основу, угаданную сервером.
  Copy-command локального отчёта спрятан во втором раскрытии «Проверить
  локально» внутри бюджета и не смешивается с блоком установки «Использовать
  через CLI» в рельсе.

- `REQ-4912`: Commit/tag/PR/MR identity следует `AGENTS.md`: имя/email динамически
  берутся только из global Git config текущего пользователя, effective author/
  committer обязаны совпадать, а агент не меняет identity/signing config и не
  подменяет автора.

## Состояния и ошибки

- GitHub: `ready`, `unavailable`; UI различает только наличие stars и
  `archived=true`, failure скрывает optional metadata.
- Budget: `ready`, `unavailable`, `invalid_graph`; partial total запрещён, если
  exact graph нельзя доказать.
- Cost: `empty`, `invalid`, `available`; amount всегда помечен estimate.
- Media: dev same-origin proxy возвращает исходный API status/content type.

## Безопасность и приватность

- GitHub URL не принимается от browser; source выводится из exact passport.
- Никакие GitHub credentials, raw response, ETag/history или private repository
  distinctions не возвращаются.
- Публичная оценка не раскрывает байты, имена файлов сверх принятого contract
  или private coordinates. Проверка владельца выполняется до чтения private graph.
- Ввод ставки на клиенте не отправляется и не сохраняется.
- Web не получает идентификаторы устройств, проекты, установленные цели
  или локальный registry.

## Совместимость и миграция

1. Добавить shared estimator и новые additive metadata/budget endpoints.
2. Перевести detail UI на них и убрать archive/blast consumers.
3. Обновить generated contracts/clients.
4. Сделать старые задания архива без эффекта, затем удалить только
   производный кэш новой миграцией. Поля старых клиентов на проводе
   удаляются согласованно до выпуска.
5. Локальный контейнер пересобирается штатным dev compose; боевая топология
   этим шагом не меняется.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-4901` | Dev compose smoke получает 200 и image content type для avatar/media через `localhost:3000`; browser image имеет `naturalWidth > 0`. |
| `REQ-4902` | Detail component test считает один metadata request; SSRF/redirect/credential negative tests проходят. |
| `REQ-4903` | API fixtures покрывают 200 active/archived, timeout, 403/404/429/5xx, malformed/private/oversized. |
| `REQ-4904` | List test доказывает ноль GitHub calls; header test показывает badge только при `archived=true`. |
| `REQ-4905` | Queue compatibility test принимает старый job; migration upgrade/downgrade затрагивает только derived cache. |
| `REQ-4906` | Generated API/Web inventory не содержит account blast radius; CLI blast-radius tests остаются зелёными. |
| `REQ-4907` | Shared fixtures дают идентичный CLI/API output для files, ZIP, UTF-8, non-UTF-8 и digest failures. |
| `REQ-4908` | Public/owner/outsider matrix и exact graph negative tests проходят без bytes/account leakage. |
| `REQ-4909` | RU/EN component tests проверяют свёрнутый итог, скрытый жаргон, empty/error и формулировку «не расход». E2e держит бюджет внутри `component-detail-rail`, не в `component-detail-main`, и порядок Author → Context budget → Use via CLI → Version history на desktop и mobile. |
| `REQ-4910` | Browser/unit tests проверяют формулу, rounding, empty/invalid input и отсутствие network/storage writes. |
| `REQ-4911` | Web не читает installed/selected state; copy-command виден только после вложенного раскрытия. |
| `REQ-4912` | Policy test/agent review проверяет global/effective identity parity и запрещает hardcode/override; signing behavior наследуется без изменений. |
