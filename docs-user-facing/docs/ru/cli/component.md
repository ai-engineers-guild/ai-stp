---
title: "Команды компонента"
description: "Группа команд component: обнаружение, паспорт, источник и публикация."
---

# Команды компонента

Компонент — одна часть сетапа, одного из восьми kind. Группа `component` —
как эта установка находит нативные файлы, записывает локальный паспорт,
привязывает внешний источник и готовит версию к публикации.

Сайт показывает каталог. Он не обнаруживает файл на этой машине, не пишет
локальный паспорт и не извлекает embedded-член. Эти шаги остаются в CLI.
Выбор, сборка и установка — другие группы.

## Дочерние страницы

| Страница | Что покрывает |
| --- | --- |
| [Обнаружение и adopt](component-discover.md) | нативное обнаружение, локальный поиск, scaffold, adopt, forget |
| [Паспорт компонента](component-passport.md) | show, suggest, update, validate, quality |
| [Источник компонента](component-source.md) | parse, resolve, search, архивные наблюдения GitHub |
| [Публикация компонента](component-publish.md) | promote, version, fork, skill validate |

Перед копированием мутирующей команды читайте дочернюю страницу. Этот обзор
называет каждый путь `component.*`. Он не заменяет happy path, поля успеха
и отказы на тех страницах.

## Что такое компонент

У компонента есть kind, точная версия `X.Y`, паспорт и источник. Закрытые
kind: `instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`,
`setting` и `cli`. `command` — именованный slash-вызов; `cli` — отдельный
исполняемый процесс. Память, правила, параметры и вспомогательные инструменты —
содержимое `instruction`, `skill` или `setting`. Это не отдельные kind.

Локальный черновик — не опубликованная версия. Adopt пути регистрирует его
здесь. Release номера `X.Y` замораживает текущий head. Публикация всё
равно требует серверный план и явное подтверждение. `author_verified` и
`component_verified` независимы: ни одно не является гарантией безопасности.

## Рабочий цикл

```text
discover / find / scaffold plan → apply
→ adopt
→ passport show → suggest → update → validate
→ source parse → resolve → evidence show
→ version release
→ component publish  or  publication plan
→ publication confirm
```

Пропускайте шаг, только если предыдущий конверт уже сделал его ненужным.
Механическую проверку не пропускайте. Не считайте `component find` поиском
по каталогу: это `registry search`. Не считайте `component publish` финальной
публичной записью: это `publication confirm` или `setup publish confirm`.

## Таблица команд

`--json` глобальный. Это не свойство одной команды. Всегда передавайте его.
`mutability` говорит, что команда делает. `confirmation` — каким токеном
подтверждается решение.

### Обнаружение и adopt

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component discover` | `read` | `none` | перечислить нативные компоненты в корнях harness и одном проекте |
| `ai-stp component find` | `read` | `none` | искать в локальном реестре; без модели, без сети |
| `ai-stp component scaffold plan` | `plan` | `none` | показать точные файлы scaffold и digest |
| `ai-stp component scaffold apply` | `apply` | `plan_digest` | создать ровно подтверждённый scaffold |
| `ai-stp component template render` | `read` | `none` | отрендерить portable-шаблон для одного harness |
| `ai-stp component adopt` | `apply` | `none` | зарегистрировать один найденный путь в локальном реестре |
| `ai-stp component forget` | `apply` | `none` | пометить зарегистрированный компонент удалённым, историю сохранить |

### Паспорт

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component passport show` | `read` | `none` | показать текущий локальный черновик паспорта |
| `ai-stp component passport suggest` | `read` | `none` | предложить факты манифеста, не записывая их |
| `ai-stp component passport update` | `apply` | `plan_digest` | добавить подтверждённый JSON-patch как новую ревизию |
| `ai-stp component passport validate` | `read` | `none` | назвать каждый структурный блокер публикации |
| `ai-stp component passport quality` | `read` | `none` | необязательные подсказки автору; trust не меняет |

### Источник

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component source parse` | `read` | `none` | разобрать внешний источник как недоверенный intent |
| `ai-stp component source resolve` | `read` | `none` | привязать GitHub-intent к одному полному commit SHA |
| `ai-stp component source search` | `read` | `none` | искать имена в каталоге; остальные полосы — по флагу |
| `ai-stp component source evidence refresh` | `apply` | `none` | обновить официальные архивные наблюдения GitHub |
| `ai-stp component source evidence show` | `read` | `none` | показать последние локальные архивные наблюдения |
| `ai-stp component source evidence history` | `read` | `none` | ограниченная append-only история наблюдений |

### Публикация

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component publish` | `plan` | `none` | извлечь один embedded-член в обычный план публикации |
| `ai-stp component version list` | `read` | `none` | все записанные версии и следующий minor |
| `ai-stp component version release` | `apply` | `none` | дать текущему head неизменяемый `X.Y` |
| `ai-stp component fork` | `apply` | `none` | скопировать одну записанную версию под новой идентичностью |
| `ai-stp component skill validate` | `read` | `none` | проверить skill-пакет по Agent Skills Specification |

## Токены подтверждения

`plan_digest` не всегда пишется как `--expected-plan-digest`. Читайте
дескриптор. `component scaffold apply` берёт `--expected-plan-digest`.
`component passport update` берёт `--expected-revision` текущего head.
Ни одна из этих команд не берёт `--confirm`. Boolean рядом с точным digest
спрашивал бы одно решение дважды.

`component adopt`, `component forget`, `component version release` и
`component fork` — `apply` с `confirmation: none`. Назвать путь, id или
версию **и есть** решение. Не выдумывайте флаг `--confirm`.

`component publish` — это `plan`. Он не делает объект публичным.
Подтверждайте возвращённый план на [Publication](publication.md).

## Чего эта группа никогда не делает

- не пишет нативное состояние harness — это делает только public provider
  через [Установку](install.md);
- не вызывает model API и не просит ключ модели;
- не кладёт секреты, тела `.env` и токены в паспорт;
- не считает `author_verified` доказательством безопасности версии;
- не восстанавливает target из backup — это `install plan --action rollback`;
- не выдаёт доступ к major-линии — это [Доступ](grant.md).

Согласие на непроверенных издателей живёт в [Согласии](consent.md), не здесь.
Поиск по каталогу — в [Реестре](registry.md). Сборка смешанного сетапа из
каталога, Git, пакета и path-источников — в [Командах сетапа](setup.md).

## Типичные отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | обязательная опция отсутствует или неверна | прочитать дескриптор; добавить названный флаг |
| `AI_STP_NOT_FOUND` | id, путь или версия здесь нет | сначала discover или find; не угадывать id |
| `AI_STP_USER_DECISION_REQUIRED` | путь отвечает более чем одному harness или kind | передать `--harness` или `--kind`, как в дескрипторе |
| `AI_STP_PLAN_STALE` | байты scaffold или паспорта изменились | построить новый план, показать, подтвердить снова |
| `AI_STP_CONFLICT` | ожидаемая ревизия больше не head | `passport show`, затем новый patch |
| `AI_STP_AUTH_REQUIRED` | облачному шагу публикации нужна сессия | `auth login`, затем повторить команду публикации |
| команды нет в machine help | этой установки её нет | остановиться; не подменять похожей командой |

Мутирующая команда без `--json` смешивает человеческий текст в stdout.
Добавьте `--json` и читайте один конверт.

## Связанные страницы

- [Обнаружение и adopt](component-discover.md)
- [Паспорт компонента](component-passport.md)
- [Источник компонента](component-source.md)
- [Публикация компонента](component-publish.md)
- [Карта команд](commands.md)
- [Компоненты](../components/index.md)
- [Публикация](../publishing/index.md)
- [Доверие и безопасность](../trust-and-safety/index.md)
- [Выбор](select.md)
- [Команды сетапа](setup.md)
- [Publication](publication.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Документация группирует команды, чтобы человек нашёл страницу. Установленный
CLI — источник флагов, схем и `next_actions`. Если страница и CLI расходятся,
следуйте CLI.
