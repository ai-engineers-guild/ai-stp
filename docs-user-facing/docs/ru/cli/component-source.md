---
title: "Источник компонента"
description: "Разобрать, разрешить и искать внешние источники компонента, читать GitHub-архивные evidence."
---

# Источник компонента

Эти команды считают внешний источник компонента недоверенным структурированным
intent, пока не привязан commit, и хранят официальные архивные наблюдения
GitHub для одной точной локальной версии.

Parse ничего не скачивает. Resolve привязывает один полный commit SHA.
Поиск имён не выбирает кандидата. Команды evidence говорят об архивном
состоянии репозитория, а не о том, безопасна ли версия.

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component source parse` | `read` | `none` | разобрать slug, GitHub-идентичность, локальный путь или коллекцию |
| `ai-stp component source resolve` | `read` | `none` | привязать GitHub-intent к одному точному полному commit SHA |
| `ai-stp component source search` | `read` | `none` | искать имена в каталоге; package и GitHub — по флагу |
| `ai-stp component source evidence refresh` | `apply` | `none` | обновить официальные архивные наблюдения GitHub для одной версии |
| `ai-stp component source evidence show` | `read` | `none` | показать последние локальные архивные наблюдения и freshness |
| `ai-stp component source evidence history` | `read` | `none` | ограниченная append-only история архивных наблюдений |

`--json` глобальный. Всегда передавайте его.

## Parse

Разобрать строку внешнего источника как структурированный intent. Результат
недоверенный, пока resolve (или другое точное доказательство) его не
привяжет.

```bash
ai-stp component source parse --source owner/repo --json
ai-stp component source parse --source https://github.com/owner/repo --json
ai-stp component source parse --source ./hooks/check --root . --json
```

`--source` обязателен. Это может быть опубликованный slug, GitHub-
идентичность, локальный путь или коллекция. `--root` нужен только чтобы
нормализовать относительный локальный путь.

Поля успеха: `kind`, `canonical`, `owner`, `ref`, `local_path`,
`collection_owner`, `collection_handle` и `provenance_proven`. `kind` —
одно из `published`, `github`, `github/exact`, `local`, `collection`.
`provenance_proven` остаётся false, пока точная идентичность не доказана.

## Resolve

Resolve привязывает GitHub shorthand или credential-free HTTPS URL к одному
lowercase SHA коммита из 40 символов.

```bash
ai-stp component source resolve --source owner/repo --json
ai-stp component source resolve \
  --source https://github.com/owner/repo \
  --commit abcdef0123456789abcdef0123456789abcdef01 \
  --json
```

`--commit` необязателен: опустите, чтобы разрешить названный ref в SHA, или
передайте точный SHA, который уже есть. `--root` только нормализует
относительный локальный путь.

Ответ той же схемы идентичности, что у parse. После успешного resolve
`kind` равен `github/exact`, а `provenance_proven` — true. Диапазон,
плавающий tag без SHA или URL с учётными данными отклоняются.

## Search

Поиск только по имени. Он никогда не выбирает кандидата и ничего не
устанавливает.

```bash
ai-stp component source search --query context7 --json
ai-stp component source search --query context7 --registry-discovery --json
```

Без `--registry-discovery` попадания — имена каталога. С флагом добавляются
поддерживаемые имена пакетов и известные GitHub-кандидаты. У каждого
попадания отдельно держатся `source`, `catalog_status`, `trust_lane`,
`author_verified` и `component_verified`. GitHub-попадание со статусом
`not_in_catalog` всё равно только имя.

Поля успеха: список кандидатов с `name`, `source` (`catalog`, `package`
или `git`), `exact_coordinate`, `stable_id`, `catalog_status`,
`trust_lane`, `author_verified`, `component_verified`.

## Evidence show, refresh, history

Архивные наблюдения GitHub — официальное наблюдение исходного репозитория:
архивирован ли он, когда наблюдение скачали, и свежо ли оно. Это не скан
безопасности.

```bash
ai-stp component source evidence show --id <stable_id> --version 1.0 --json
ai-stp component source evidence refresh --id <stable_id> --version 1.0 --json
ai-stp component source evidence history --id <stable_id> --version 1.0 --json
ai-stp component source evidence history --id <stable_id> --version 1.0 --limit 20 --json
```

`--id` и `--version` обязательны. `--version` — точный записанный `X.Y`.
`--limit` в history — сколько новейших наблюдений вернуть, от 1 до 100.

`refresh` — `apply`: пишет новое наблюдение. У него `confirmation: none`.
Назвать точные id и версию **и есть** решение.

Поля успеха show и refresh: `stable_id`, `version`, `passport_digest`,
`source_repository`, `repository_id`, `repository_full_name`,
`repository_state`, `archived`, `fetched_at`, `expires_at`, `freshness`,
`observation_id`. `freshness` — `fresh`, `stale` или `unavailable`.
`repository_state` — `active`, `archived` или `unavailable`. History
возвращает ограниченный список этих наблюдений.

## Happy path

```text
component source parse --source owner/repo
→ component source resolve --source owner/repo
→ component source search --query <name>
→ setup update plan  or  component adopt
```

Для уже выпущенной версии:

```text
component source evidence show --id <id> --version 1.0
→ component source evidence refresh --id <id> --version 1.0   # если stale
→ component source evidence history --id <id> --version 1.0
```

## Именованные поля успеха

| Команда | Какие поля читать |
| --- | --- |
| `parse` / `resolve` | `kind`, `canonical`, `provenance_proven`, `ref` |
| `search` | у каждого кандидата `name`, `source`, `catalog_status`, `trust_lane` |
| `evidence show` / `refresh` | `freshness`, `archived`, `repository_state`, `fetched_at` |
| `evidence history` | ограниченный список наблюдений |

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | нет `--source`, `--id` или `--version`, или значение неверно | исправить запрос; диапазон — не версия |
| `AI_STP_NOT_FOUND` | локального объекта или версии нет | `component version list --id <id>` |
| `AI_STP_DEPENDENCY_UNAVAILABLE` | GitHub или реестр недоступны | повторять только если `retryable: true`; иначе работать из cache |
| `AI_STP_PRECONDITION_FAILED` | источник — не credential-free GitHub-идентичность | убрать учётные данные; HTTPS без userinfo |
| `freshness: stale` | последнее наблюдение истекло | `evidence refresh` для этой точной версии |
| `freshness: unavailable` | официальный архив наблюдать не удалось | прочитать `repository_state`; не выдумывать замену |
| поиск без `--registry-discovery` | полосы package и GitHub не запрашивались | передать флаг, если эти полосы имелись в виду |
| считать попадание поиска pin | поиск никогда не выбирает | дальше resolve или plan точной координаты |

Не кладите токены в `--source`. Нигде в этой группе не передавайте
`NAME=value`. Не выдумывайте `--commit` у parse: эта опция есть только у
resolve.

## Связанные страницы

- [Команды компонента](component.md)
- [Обнаружение и adopt](component-discover.md)
- [Паспорт компонента](component-passport.md)
- [Публикация компонента](component-publish.md)
- [Команды сетапа](setup.md)
- [Реестр](registry.md)
- [Публикация](../publishing/index.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды источника, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
