---
title: "Публикация компонента"
description: "Выпустить версию X.Y, сделать fork, проверить skill-пакет и выделить встроенный компонент."
---

# Публикация компонента

Эти команды замораживают локальный head как неизменяемый `X.Y`, копируют
версию под новой идентичностью, проверяют skill-пакет по Agent Skills
Specification и извлекают один embedded-член сетапа в обычный план
публикации.

Сами по себе они не делают каталог публичным. `component publish` — это
`plan`. Публичная запись — подтверждение на [Publication](publication.md)
или `setup publish confirm`, когда наружу уходит весь граф.

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component version list` | `read` | `none` | все записанные версии и следующий minor |
| `ai-stp component version release` | `apply` | `none` | дать текущему head неизменяемый `X.Y`; minor, если нет `--major` |
| `ai-stp component fork` | `apply` | `none` | скопировать одну записанную версию под новой идентичностью |
| `ai-stp component skill validate` | `read` | `none` | назвать каждое отклонение от Agent Skills Specification |
| `ai-stp component publish` | `plan` | `none` | извлечь один embedded-компонент в план публикации |

`--json` глобальный. Всегда передавайте его.

## Version list

```bash
ai-stp component version list --id <stable_id> --json
```

Поля успеха: `stable_id`, `versions` (у каждой `version`,
`passport_digest`, `revision_id`, `created_at`), `next_minor`,
`publishable`, `publish_reason`, `forked_from`, `forked_from_version`.
`next_minor` считается из сохранённой истории. Поля `next_major` нет:
открыть major-линию — решение, а не подсказка.

## Version release

Release даёт текущему head паспорта неизменяемый двухцелый номер. По
умолчанию — следующий minor. `--major` открывает следующую major-линию.
Этот boolean **и есть** решение о major-линии. Второго `--confirm` нет.

```bash
ai-stp component version release --id <stable_id> --json
ai-stp component version release --id <stable_id> --major --json
```

Выданный номер не переиспользуется и не переписывается. Ответ той же формы
version-line, что у `version list`, теперь с новым `X.Y`. Если собираетесь
публиковать, перед release проверьте паспорт.

## Fork

Fork копирует одну записанную версию под новой идентичностью. Оригинал не
трогается.

```bash
ai-stp component fork --id <stable_id> --version 1.0 --json
```

`--id` и `--version` обязательны. `--version` — точный копируемый `X.Y`.
Ответ — линия версий **новой** идентичности: `stable_id` (новый),
`forked_from`, `forked_from_version`, `versions`, `next_minor`.

## Skill validate

Проверить каталог по Agent Skills Specification. Это read. Называет каждое
отклонение. Не adopt, не патчит и не публикует.

```bash
ai-stp component skill validate --path ./components/demo-skill --json
```

Поля успеха: `conforms`, `name`, `description`, `findings`,
`extension_directories`, `other_entries`, `packaged_as`. У каждого finding
есть `code` (вида `SK000`), `at` и `summary`. `conforms: false` со списком
finding — успешный отчёт, а не упавшая команда.

Это не собственный Agent Skill CLI (`ai-stp skill …`). Тот skill описан на
[Agent Skill CLI](skill.md). Kind `skill` — это компонент.

## Component publish

Извлечь один **embedded**-компонент из локального сетапа в обычный план
публикации. У членов каталога уже есть издатель; эта команда — для члена,
который живёт только внутри сетапа.

```bash
ai-stp component publish \
  --from-setup <setup_id> \
  --setup-version 1.0 \
  --component-id <embedded_id> \
  --json
```

`--from-setup`, `--setup-version` и `--component-id` обязательны.
`--component-id` — точный embedded-идентификатор, никогда не display name.
`--attestation-file` повторяемый: каждый путь — полное локально подписанное
attestation, привязанное к продвигаемой версии.

Ответ — план продвижения: `setup_id`, `setup_version`,
`source_component_id`, `catalog_stable_id`, `catalog_version`, `plan_id`,
`plan_hash`, `state`, `reused_passport`, `still_embedded`. Подтверждайте
его через `publication confirm --plan-id … --plan-hash … --confirm`.
Embedded-член остаётся embedded, пока подтверждение не завершится.

## Happy path

Из локального черновика:

```text
component passport validate --id <id>
→ component version release --id <id>
→ publication plan --id <id> --version <X.Y>
→ publication confirm --plan-id <plan> --plan-hash <hash> --confirm
```

Из embedded-члена сетапа:

```text
component publish --from-setup <setup> --setup-version <X.Y> --component-id <id>
→ publication status --plan-id <plan>
→ publication confirm --plan-id <plan> --plan-hash <hash> --confirm
```

Для skill-пакета, который ещё не adopt:

```text
component skill validate --path <dir>
→ component adopt --path <dir>
→ component passport validate --id <id>
```

## Именованные поля успеха

| Команда | Какие поля читать |
| --- | --- |
| `version list` / `release` / `fork` | `stable_id`, `versions`, `next_minor`, `forked_from` |
| `skill validate` | `conforms`, `findings` |
| `publish` | `plan_id`, `plan_hash`, `catalog_stable_id`, `catalog_version`, `still_embedded` |

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | нет обязательного id, версии или пути | прочитать дескриптор |
| `AI_STP_NOT_FOUND` | объекта, версии или embedded-члена здесь нет | `version list` или `select graph` |
| `AI_STP_PRECONDITION_FAILED` | паспорт не готов, или attestation не привязано | `passport validate`; подписать через `attestation sign` |
| `AI_STP_AUTH_REQUIRED` | продвижение на сервер требует сессии | `auth login`, затем снова `component publish` |
| `AI_STP_PERMISSION_DENIED` | этот аккаунт не может публиковать этот объект | проверить owner и grants |
| `conforms: false` | skill-пакет отклоняется от спецификации | прочитать каждый `SK…` finding; не adopt как прошедший |
| считать `component publish` публичным | это plan | подтвердить через `publication confirm` |
| выдумывать `--confirm` у release | такого флага нет | `--major` — единственное дополнительное решение |

Публичная версия должна приходить из публичного репозитория GitHub на
точном commit и subpath. Черновики только локально остаются локальными,
пока такого provenance нет.

## Связанные страницы

- [Команды компонента](component.md)
- [Паспорт компонента](component-passport.md)
- [Источник компонента](component-source.md)
- [Publication](publication.md)
- [Команды сетапа](setup.md)
- [Публикация](../publishing/index.md)
- [Публикация и авторство](../publishing/authoring.md)
- [Проверки безопасности](../security-checks.md)
- [Agent Skill CLI](skill.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды публикации, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
