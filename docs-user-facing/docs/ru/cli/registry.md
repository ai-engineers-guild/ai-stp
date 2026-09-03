---
title: "Реестр"
description: "Искать и показывать публичный каталог, загружать точные версии, получать граф сетапа и импортировать локальные снапшоты SX или APM."
---

# Реестр

Команды реестра читают публичный каталог без учётной записи, загружают
точные опубликованные байты в локальный кэш, получают один граф сетапа
для офлайн-компиляции и импортируют локальный снапшот SX или APM
только в локальный реестр. Они не применяют сетап и не записывают
таргет харнеса.

Результат поиска — это кандидат, а не разрешение на установку. Проверьте
харнес, точную версию `X.Y`, линию доверия и обе независимые оси
верификации, прежде чем что-либо выбирать.

## Команды

| Команда | Мутабельность | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp registry search` | `read` | `none` | Поиск по публичному каталогу без учётной записи. |
| `ai-stp registry show` | `read` | `none` | Показать один объект каталога и его опубликованные версии. |
| `ai-stp registry version` | `read` | `none` | Показать одну точную опубликованную версию и её верифицированный паспорт. |
| `ai-stp registry fetch` | `apply` | `none` | Загрузить точные байты одной опубликованной версии в локальный кэш. |
| `ai-stp registry acquire` | `apply` | `none` | Получить один точный опубликованный граф сетапа для локальной офлайн-компиляции. |
| `ai-stp registry port discover` | `read` | `none` | Найти совместимые снапшоты SX и APM под одним указанным локальным корнем. |
| `ai-stp registry port inspect` | `read` | `none` | Инспектировать одно отображение setup-store без импорта и без запуска его CLI. |
| `ai-stp registry port plan` | `plan` | `none` | Предпросмотр локального импорта setup-store с привязкой к точным байтам манифеста. |
| `ai-stp registry port import` | `apply` | `plan_digest` | Импортировать подтверждённый точный снапшот SX или APM только в локальный реестр. |

`--kind` обязателен для `search`, `show`, `version` и `fetch`. Значение —
`component` или `setup`. `--id` обязателен для `show`, `version`,
`fetch` и `acquire`. `--version` обязателен для `version`, `fetch`
и `acquire`. Команды port требуют `--root`; inspect, plan и
import также требуют `--adapter` (`sx` или `apm`). Import требует
`--expected-plan-digest`.

## Типичный путь

Анонимные чтения каталога:

```bash
ai-stp registry search --kind component --json
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry version --kind component --id <stable_id> --version <version> --json
```

`<stable_id>` — стабильный идентификатор объекта. `<version>` —
точная `X.Y`. Диапазон — это не ссылка.

Чтобы поместить эти точные байты в локальный кэш, а затем получить граф
сетапа:

```bash
ai-stp registry fetch --kind component --id <stable_id> --version <version> --json
ai-stp registry acquire --id <stable_id> --version <version> --json
```

`acquire` предназначен для опубликованного *сетапа*. Его `--id` — это
идентификатор сетапа.

Для импорта локального снапшота setup-store, без обращения к внешнему
хранилищу и без записи таргета харнеса:

```bash
ai-stp registry port discover --root <root> --json
ai-stp registry port inspect --root <root> --adapter sx --json
ai-stp registry port plan --root <root> --adapter sx --json
ai-stp registry port import --root <root> --adapter sx --expected-plan-digest <plan-digest> --json
```

`<plan-digest>` — это дайджест, который вернула `port plan`. Если байты
снапшота изменились, дайджест больше не совпадает и импорт отклоняется.

Если сеть недоступна, чтение может ответить из кэша и сообщит об этом
в `source`. Читайте `checked_at`. Не принимайте попадание в кэш за живой
каталог.

## Чтения каталога

### `registry search`

Поиск по публичному каталогу без учётной записи.

```bash
ai-stp registry search --kind component --json
```

`--kind` обязателен и принимает значение `component` или `setup`. Необязательные
флаги запроса, курсора, лимита и экспериментальной линии есть в machine help.
Они не обязательны, поэтому здесь не копируются.

Поля успешного `data`:

| Поле | Что это |
| --- | --- |
| `kind` | `component` или `setup` |
| `items` | страница авторитетной линии |
| `experimental` | экспериментальная линия, если запрошена |
| `next_cursor` | непрозрачный курсор для следующей страницы, или пустой |
| `source` | `online` или `cache` |
| `checked_at` | когда платформа в последний раз подтвердила эти байты |
| `schema_version` | мажорная версия схемы этого отчёта |

Карточка — это не паспорт уровня объекта. Факты последней версии
скопируются из паспорта этой версии. `author_verified` и
`component_verified` независимы. См.
[Каталог](../catalog/index.md) и
[Доверие и безопасность](../trust-and-safety/index.md).

### `registry show`

Показать один объект каталога и его опубликованные версии.

```bash
ai-stp registry show --kind component --id <stable_id> --json
```

Успешный `data` содержит `kind`, `summary`, `versions`, `source`,
`checked_at` и `schema_version`. `versions` — это опубликованная линия,
а не локальный черновик.

### `registry version`

Показать одну точную опубликованную версию и её верифицированный паспорт.

```bash
ai-stp registry version --kind component --id <stable_id> --version <version> --json
```

Успешный `data` содержит `kind`, `lifecycle`, `passport`,
`passport_digest`, `published_at`, `trust`, `source`, `checked_at`
и `schema_version`.

`trust` несёт `author_verified`, `component_verified` и
`trust_lane` (`authoritative` или `experimental`). Ни один флаг верификации
не может быть вычислен из другого. `authoritative` дополнительно
требует оба, и эта импликация не заменяет чтение флагов.

## Записи каталога в локальный кэш

### `registry fetch`

Загрузить точные байты одной опубликованной версии в локальный кэш.

```bash
ai-stp registry fetch --kind component --id <stable_id> --version <version> --json
```

Записывает только в локальный кэш и больше никуда. Байты неизменяемы
и адресуются по содержимому, поэтому второй вызов — это no-op. Это не
установка.

Поля успешного `data`:

| Поле | Что это |
| --- | --- |
| `kind` | `component` или `setup` |
| `stable_id` | объект, который вы загрузили |
| `version` | точная `X.Y` |
| `digest` | дайджест содержимого байтов |
| `path` | где теперь находятся эти байты |
| `size_bytes` | длина файла |
| `source` | `online` или `cache` |
| `checked_at` | когда байты были подтверждены |
| `schema_version` | мажорная версия схемы этого отчёта |

Файл по `path` хэшируется в `digest` и имеет длину `size_bytes`. В этом
смысл конверта.

### `registry acquire`

Получить один точный опубликованный граф сетапа для локальной офлайн-компиляции.

```bash
ai-stp registry acquire --id <stable_id> --version <version> --json
```

`--id` и `--version` обязательны. Материализует один опубликованный
сетап и каждый точный компонент, который он фиксирует. Это не `install apply`.
Следующий честный шаг — [Select](select.md) или [Install](install.md)
на локальном графе.

Успешный `data` содержит `stable_id`, `version`, `harness_id`,
`passport_digest`, `artifact_digest`, `components`, `source`,
`checked_at` и `schema_version`. Каждый полученный компонент содержит
`stable_id`, `version`, `passport_digest` и `artifact_digest`.

Если опубликованный граф фиксирует две версии одного компонента, или
паспорт компонента отличается от точной ссылки сетапа, команда
отклоняет с `AI_STP_CATALOG_INTEGRITY` или `AI_STP_CONFLICT`. Не
«выбирайте один» вручную.

## Локальный порт setup-store

Эти четыре команды обращаются к директории, которую вы укажете. Они не
запускают чужой CLI. Они не изменяют внешнее хранилище. Они не записывают
таргет харнеса. `adapter` — это `sx` или `apm`.

### `registry port discover`

Найти совместимые снапшоты SX и APM под одним указанным локальным корнем.

```bash
ai-stp registry port discover --root <root> --json
```

Успешный `data` содержит `root`, `stores` и `diagnostics`. Каждое
хранилище содержит `adapter`, `contract_version`, `root`, `manifest`,
`snapshot_digest` и `cli_status` (`available`, `absent` или
`not_required`).

### `registry port inspect`

Инспектировать одно отображение setup-store без импорта и без запуска его CLI.

```bash
ai-stp registry port inspect --root <root> --adapter sx --json
```

Успешный `data` содержит `descriptor`, `mappings`, `unknown_fields`
и `diagnostics`. Неизвестные поля перечислены, а не импортированы молча.

### `registry port plan`

Предпросмотр локального импорта setup-store с привязкой к точным байтам
манифеста.

```bash
ai-stp registry port plan --root <root> --adapter sx --json
```

Это `plan`. Сам по себе он не имеет эффекта. Успешный `data` содержит
`plan_digest`, `inspection`, `importable_count`, `omitted_count`,
`conflicts` и `trust_consequences`.

`trust_consequences` — замкнутый список. Типичные элементы:
`local_only`, `author_verified_false`, `component_verified_false`,
`external_store_unchanged` и `harness_target_unchanged`. Импорт не
становится верифицированным платформой, попав через этот порт.

### `registry port import`

Импортировать подтверждённый точный снапшот SX или APM только в локальный
реестр.

```bash
ai-stp registry port import --root <root> --adapter sx --expected-plan-digest <plan-digest> --json
```

`--expected-plan-digest` обязателен. Подтверждение — это `plan_digest`:
импортировано может быть только то, что уже описано. Если байты
изменились, постройте новый план.

Успешный `data` содержит `plan_digest`, `imported`,
`external_store_changed` (всегда `false`) и
`harness_target_changed` (всегда `false`). Каждый импортированный объект содержит
`external_id`, `stable_id`, `revision_id` и `state` (`imported` или
`already_imported`).

## Что содержит успешный конверт

Каждая команда возвращает поля, указанные в её разделе. Каждый конверт
также несёт `ok`, `warnings`, `next_actions`, `request_id`,
`operation_id` и `schema_version`.

`source` при чтениях каталога — `online` или `cache`. Кэш — это успешный
ответ, когда платформа уже подтвердила байты. Это не живое обновление.
Читайте `checked_at`.

Если `catalog.enabled` — false, команды каталога отклоняют с
`AI_STP_DEPENDENCY_UNAVAILABLE`. Это конфигурация, а не сбой.
См. [Конфигурация](config.md).

## Что эти команды никогда не делают

- не применяют сетап и не записывают таргет харнеса;
- не запускают чужой CLI SX или APM;
- не изменяют внешнее хранилище сетапов;
- не принимают `author_verified` за `component_verified`;
- не принимают диапазон версий вместо точной `X.Y`;
- не пропускают согласие, eligibility или дайджест плана установки;
- не помещают секреты в паспорт или карточку поиска.

## Типичные отказы

| Что вы видите | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` отсутствует `--kind` | search, show, version и fetch требуют его | `--kind component` или `--kind setup` |
| `AI_STP_VALIDATION_ERROR` отсутствует `--id` / `--version` | эта команда именована одним точным объектом | передайте обязательные опции |
| `AI_STP_DEPENDENCY_UNAVAILABLE` каталог выключен | `catalog.enabled` — false | `config show --json`; не принимайте это за простой |
| `source: cache` | платформа не была доступна | читайте `checked_at`; не принимайте за живой каталог |
| `AI_STP_CATALOG_INTEGRITY` | опубликованные байты или паспорта не совпадают | остановитесь; не устанавливайте из сломанного графа |
| `AI_STP_CONFLICT` две версии одного компонента | граф сетапа не точен | не выбирайте победителя вручную |
| `AI_STP_USER_DECISION_REQUIRED` при port import | `--expected-plan-digest` отсутствовал | передайте дайджест, который вернула `port plan` |
| устаревший дайджест плана | байты снапшота изменились | `port plan` заново, затем импортируйте новый дайджест |
| `AI_STP_VALIDATION_ERROR` отсутствует `--root` / `--adapter` | команды port требуют явного хранилища | `--root <root> --adapter sx` или `apm` |

## Связанные страницы

| Страница | Зачем |
| --- | --- |
| [Каталог](../catalog/index.md) | как читать карточку |
| [Веб-каталог](../web/catalog.md) | те же объекты на сайте |
| [Доверие и безопасность](../trust-and-safety/index.md) | линии доверия и оси верификации |
| [Согласие](consent.md) | неверифицированные издатели и мажорные линии |
| [Select](select.md) | eligibility и предложение после fetch |
| [Install](install.md) | план, одобрение, применение |
| [Команды сетапа](setup.md) | композиция и импорт нативной конфигурации |
| [Вход](auth.md) | `link web` для канонического URL |
| [Быстрый старт для человека](../quickstart/human.md) | первое чтение каталога |

!!! note "Флаги из `ai-stp help --agent --json`"
    Если `help --agent` расходится с флагом на этой странице, CLI выигрывает.
    Необязательные флаги здесь не перечислены. Читайте их из дескриптора.
    Команды каталога требуют `--kind` там, где это указано в таблице. Port
    import требует `--expected-plan-digest`.
