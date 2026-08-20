---
description: "ADR-0096: On-demand GitHub metadata, локальный blast radius и shared context estimator."
last_verified: "2026-08-15"
---

# ADR-0096: On-demand metadata and local impact boundary

Статус: предложено.

## Контекст

`ADR-0094` ввёл server-owned archive history и account blast radius для Web.
Реализация оказалась шире нужного продукта: archive panel виден при active/
unavailable repository, worker постоянно поддерживает производный cache, а Web
показывает все active devices аккаунта без доказанной связи с installation.
Одновременно CLI уже владеет точным local blast radius и context/cost report.
Локальный SaaS standalone image был ошибочно подставлен вместо dev runtime и
потерял dev-only `/v1` rewrite, хотя media bytes остались доступны в API.

## Варианты

1. Доработать periodic archive и account blast модели. Сохраняет текущий код,
   но поддерживает ненужные jobs/storage и не исправляет ownership boundary.
2. Перенести GitHub вызов прямо в browser и оставить server impact. Меньше кода,
   но произвольный external fetch/CORS/rate-limit оказываются на клиенте.
3. Читать ограниченную server metadata по exact coordinate по запросу, вернуть
   blast radius в границу только CLI и вынести общий чистый context estimator
   для честной public setup projection.

## Решение

Выбран вариант 3.

- GitHub stars/archive читаются одним best-effort request при открытии detail;
  source разрешается сервером из exact passport. UI показывает только stars и
  условный `Archived` badge рядом с GitHub link.
- Periodic archive observation/history и отдельный evidence panel прекращаются.
- Blast radius остаётся исключительно локальным CLI report. Server/Web surfaces
  удаляются; Web не перечисляет devices, projects или installations.
- Детерминированный context estimator становится shared domain implementation
  для CLI и server. Web получает только абсолютный budget видимой exact setup;
  local baseline/delta остаётся CLI.
- Cost в Web считается client-only из явно введённой ставки и не называется
  actual usage.
- Локальная среда использует dev compose/Next rewrite без Caddy. Production path
  split остаётся обязанностью Caddy и этим решением не меняется.

## Последствия

Удаляются лишние задания, хранилища и поверхности API и интерфейса, но нужен
путь совместимости для уже поставленных в очередь заданий архива и прямой
миграции только производных таблиц. Метаданные GitHub
могут отсутствовать из-за ограничения частоты или сбоя транспорта и при этом
не ломают карточку. Карточка создаёт один внешний запрос, список каталога —
ни одного. Общий estimator требует переноса реальной логики, а не третьей
копии. Оценка в Web воспроизводима для видимых серверу артефактов, но
намеренно не знает локальную установленную основу.

`ADR-0094` заменён этим решением в частях GitHub archive read model и account
blast-radius delivery. Его canonical copy/deep-link и другие consumer решения
продолжают действовать.

## Условия пересмотра

Решение пересматривается при появлении доказанного server-owned installation
graph, обязательного GitHub SLA/credentialed quota, actual model usage telemetry
или безопасного local-agent bridge с отдельным контрактом согласия пользователя.
