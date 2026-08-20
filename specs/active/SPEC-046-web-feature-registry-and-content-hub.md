---
description: "SPEC-046: Типизированные deploy-профили web и отключаемый git-native content hub."
last_verified: "2026-08-12"
---

# SPEC-046: Web feature registry и content hub

## Цель

Web получает один типизированный реестр deploy-поверхностей. Выключенная поверхность
одновременно исчезает из human и machine маршрутов, навигации, sitemap, discovery и
клиентских entry points, а неизвестная или неполная конфигурация останавливает сборку.
Первый потребитель реестра — хранимый в Git раздел материалов со статьями, блогом, историей изменений и
release notes на русском и английском.

## Границы

Входят: версионируемые YAML-профили развёртывания, переопределения окружения при сборке, строгая валидация,
типизированные ключи, human/machine route gates, общая навигация, sitemap/robots,
`llms.txt`, Atom, четыре типа контента и сценарии промышленной сборки включённого и
выключенного профиля.

Не входят: группы пользователей, процентное включение, A/B-тесты, удалённый опрос,
admin UI, база или Redis для флагов, runtime-включение после сборки, permission/authz
и внешняя CMS.

## Термины

- `Feature key` — стабильный типизированный идентификатор deploy-поверхности.
- `Deploy profile` — полный набор boolean-значений всех feature keys.
- `Compiled features` — результат выбора профиля и переопределений сборки, встроенный
  в точный веб-артефакт.
- `Feature consumer` — маршрут, navigation item, discovery entry или другой участок,
  чьё наблюдаемое поведение меняется ключом.
- `Content hub` — публичная поверхность на основе Git с типами `article`, `blog_post`,
  `changelog` и `release_notes`.

## Требования

- `REQ-4601`: `apps/web/config/features.yaml` имеет `schema_version`,
  `default_profile` и полный набор profiles. Неизвестные поля, profiles, feature keys,
  duplicate keys, пропущенные keys и не-boolean значения отклоняются до Next build.
- `REQ-4602`: Допустимые feature keys принадлежат TypeScript registry. YAML хранит
  только значения profiles и не создаёт новые keys.
- `REQ-4603`: `AI_STP_WEB_PROFILE` выбирает profile при сборке. Явный
  `AI_STP_FEATURE_<KEY>` со значением `true` или `false` имеет приоритет; неизвестный
  или недопустимое переопределение завершает сборку отказом.
- `REQ-4604`: Compiled feature set является частью идентичности web artifact.
  Runtime environment не включает отсутствующую в artifact поверхность и не меняет
  profile после `next build`.
- `REQ-4605`: Выключенная human-поверхность отвечает настоящим HTTP 404 и получает
  `noindex`; ссылка отсутствует в шапке, подвале и клавиатурной навигации до гидратации.
- `REQ-4606`: Machine route той же выключенной поверхности отвечает 404. Human и
  machine navigation строятся из одной модели и фильтруются одним feature set.
- `REQ-4607`: Sitemap, robots, `llms.txt`, `llms-full.txt`, RSS/Atom и другие
  поверхности обнаружения не публикуют выключенный раздел.
- `REQ-4608`: Server-only loader и YAML parser не входят в client bundle. Client
  components получают только безопасные compiled booleans или уже отфильтрованные
  navigation items.
- `REQ-4609`: Каждый объявленный feature key имеет owner, issue и хотя бы один
  проверяемый consumer; dormant keys запрещены.
- `REQ-4610`: `content_hub` является первым key. При включении доступны index и
  detail pages для `article`, `blog_post`, `changelog`, `release_notes`, по одному
  примеру каждого типа и локали.
- `REQ-4611`: запись материала имеет тип, slug, locale, заголовок, описание, дату
  публикации, теги, признак черновика и тело. Неизвестные поля, дубликаты `(locale,type,slug)`,
  будущая/невалидная дата и draft в public projection отклоняются или исключаются
  детерминированно.
- `REQ-4612`: Content routes имеют canonical, hreflang, Open Graph и подходящий
  JSON-LD type. Draft/internal entries не индексируются и отвечают 404.
- `REQ-4613`: Content index и detail имеют содержательно отличную machine-проекцию,
  построенную из того же source, а links остаются в machine URL той же локали.
- `REQ-4614`: RSS содержит только опубликованные entries включённого content hub,
  использует абсолютные canonical URL и не содержит secrets, private data или drafts.
- `REQ-4615`: Production scenario строит два standalone artifacts: `public_saas`
  даёт human/machine 200, nav/sitemap/feed entries; `self_hosted` даёт human/machine
  404 и отсутствие всех discovery/navigation entries.
- `REQ-4616`: RU/EN имеют одинаковые типы и slugs либо явную fallback policy. MVP
  использует строгие пары без автоматического fallback.
- `REQ-4617`: Реестр содержит ровно два продуктовых профиля: `public_saas` включает
  `content_hub` и `saas_public_pages`, а `self_hosted` выключает их. Во втором профиле
  contact и legal отсутствуют в human/machine routes, header, footer, keyboard
  navigation, sitemap и robots.

## Состояния и ошибки

Ошибка configuration является build failure с именем поля/profile/key без вывода
полного environment. Неизвестный content type или slug отвечает 404. Выключенная
поверхность не деградирует до пустой страницы или `200 noindex`.

## Безопасность и приватность

Feature flags не являются authz и не обходят API authorization. YAML и Markdown
являются repository-owned bounded input. Raw HTML и опасные URL не публикуются.
Значения окружения, cookie, токены OAuth и закрытые записи не попадают в сгенерированные
metadata, feeds, logs или client bundles.

## Совместимость и миграция

Существующие routes и API не меняются. Rollback выбирает profile без `content_hub`
или возвращает предыдущий точный image; runtime mutation artifact не применяется.
Удаление key требует одновременного удаления всех consumers и profile values.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-4601` | Модульные тесты отклоняют неполный YAML, неизвестные поля и неверные значения. |
| `REQ-4602` | Тест реестра доказывает, что YAML не может объявить новый ключ. |
| `REQ-4603` | Модульные тесты проверяют выбор профиля, приоритет переопределения и отказ на неверном значении. |
| `REQ-4604` | Две отдельные production-сборки сохраняют выбранное состояние после запуска. |
| `REQ-4605` | Playwright проверяет HTTP 404, `noindex` и отсутствие ссылки в исходном HTML. |
| `REQ-4606` | Playwright проверяет machine 404, а тест навигации — общую модель. |
| `REQ-4607` | Playwright проверяет sitemap, robots, `llms.txt`, `llms-full.txt` и Atom в обоих профилях. |
| `REQ-4608` | Анализ production bundle не находит YAML parser и server loader в клиентских chunks. |
| `REQ-4609` | Static consumer coverage test. |
| `REQ-4610` | Тест источника подтверждает четыре типа в обеих локалях. |
| `REQ-4611` | Модульные тесты источника проверяют schema, уникальность, даты и черновики. |
| `REQ-4612` | Браузерный сценарий проверяет metadata, JSON-LD и 404 черновика. |
| `REQ-4613` | Браузерный сценарий сравнивает human и machine index/detail из одного источника. |
| `REQ-4614` | Тест Atom проверяет только опубликованные записи и абсолютные canonical URL. |
| `REQ-4615` | Две последовательные standalone-сборки с одной сценарной suite. |
| `REQ-4616` | Locale parity test по content registry. |
| `REQ-4617` | Две локальные production-сборки и Playwright проверяют SaaS и self-hosted поверхности. |
