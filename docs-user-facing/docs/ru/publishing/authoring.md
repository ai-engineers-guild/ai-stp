---
title: Публикация и авторство
description: "Подготовка repository-backed компонентов и сетапов к публикации."
---

# Авторство компонента или сетапа

Авторство — локальная работа, связанная digest: собрать дерево, заполнить
только подтверждённые факты, закрепить точный публичный GitHub commit,
проверить паспорт, выпустить `X.Y`, затем пройти
[Публикацию](index.md). Секреты, приватные пути, кэши и generated output не
должны попадать в паспорт.

Опубликованная версия — неизменяемый `X.Y`, не SemVer. Изменение байтов
означает новую версию.

## Scaffold

Сначала просмотрите каждый файл и digest, затем примените те же входы с
точным digest плана. Назначения ещё не должно существовать.

```bash
ai-stp component scaffold plan \
  --type skill \
  --language none \
  --harness portable \
  --name playwright-checks \
  --output ./playwright-checks \
  --json

ai-stp component scaffold apply \
  --type skill \
  --language none \
  --harness portable \
  --name playwright-checks \
  --output ./playwright-checks \
  --expected-plan-digest <digest> \
  --json
```

`--type` — один из восьми видов. Декларативные виды (`instruction`, `skill`,
`command`, `agent`, `setting`) принимают `--language none`. Исполняемые `mcp`
и `plugin` принимают `python`, `typescript`, `javascript`, `rust`, `go` или
`dart-flutter`. `hook` не принимает Rust или Go: provider не делает скрытую
сборку исходников.

`--harness` — `portable` или один конкретный харнесс. Если у харнесса нет
самостоятельной нативной формы для этого вида, план отклоняется до любой
записи. `setting` требует конкретный харнесс. Apply инициализирует git,
если каталог ещё не внутри worktree; git не входит в digest плана.

Каталог `component-scaffold/5` содержит:

```text
playwright-checks/
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
├── source/                  # канон; portable adopt переносит это
└── projections/<harness>/   # только если --harness конкретный
```

У hook дополнительно есть `source/hook-source.json` (событие, порядок, блокирующий
failure, handler) и спроецированный нативный манифест. Plugin с каталогом
манифеста получает продуктовый манифест и заметку `skills/`, без заглушки
`activate_plugin`. Plugin для OpenCode и Pi — один модуль JS/TS, без
выдуманного манифеста. `setting` требует конкретный харнесс.

`discover` / `adopt` переносят `source/` для portable и
`projections/<harness>/` для конкретного харнесса, а не весь авторский
каталог.

`setup scaffold plan` / `apply` создают физический каталог сетапа для одного
харнесса: черновик `setup.json`, черновик `setup-passport.json`, вложенные
`components/<member>/` с одним git-корнем и пустой `projections/<harness>/`
до отдельной команды экспорта. Вложенные члены указывают на сгенерированную
проекцию и задают `managed_paths`. Перед `setup compose` замените каждый
маркер `TODO(ai-stp-scaffold):` и добавьте tags: compose отказывает черновику.
Compose пишет SQLite. Compose — это не install.

## Паспорт

Паспорт scaffold — локальный patch: без выдуманного источника, без секретов,
без разрешения на распространение (`NOASSERTION`, пока вы не проверите
лицензию).

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <source_path> --json
ai-stp component passport show --id <stable_id> --json
ai-stp component passport suggest --id <stable_id> --json
ai-stp component passport update --id <stable_id> --expected-revision <rev> --from <patch.json> --json
ai-stp component passport validate --id <stable_id> --json
ai-stp component passport quality --id <stable_id> --json
```

`validate` перечисляет все структурные блокеры публикации. `quality` —
необязательные подсказки автору; он не меняет доверие и готовность.

Для `required_env` записывайте имена и назначение, никогда значения.

## Точный GitHub commit

`component source parse` — недоверенное намерение. `github/exact` становится
только полный lowercase SHA commit.

```bash
ai-stp component source parse --source https://github.com/example/repo --json
ai-stp component source resolve --source https://github.com/example/repo --commit <40-char-sha> --json
```

Ветка, тег, короткий SHA, URL с учётными данными, управляющие символы,
абсолютный subpath или выход через `..` отклоняются. Точная идентичность ещё
не доказывает digest содержимого; это даёт последующий путь import/adopt.

Обновляйте архивные GitHub-доказательства только после того, как версия уже
есть локально:

```bash
ai-stp component source evidence show --id <stable_id> --version 1.0 --json
ai-stp component source evidence refresh --id <stable_id> --version 1.0 --json
```

## Без секретов

Не кладите токены, пароли, закрытые ключи, OAuth refresh token или тела
`.env` в:

- паспорт;
- файлы `source/` или `projections/<harness>/`, которые будут опубликованы;
- логи, фикстуры или примеры README с живыми значениями.

Если харнессу нужна учётная запись, паспорт может сказать, что требуется
именованная переменная. Значение живёт в системном хранилище секретов или в
окружении оператора — никогда в артефакте.

`setting` — не место, чтобы прятать секреты. См.
[`setting`](../components/setting.md).

## Проверка только для skill

Из восьми видов независимая спецификация есть только у `skill`. Проверяйте
**пакет** (каталог с `SKILL.md` в корне), а не всё авторское дерево:

```bash
ai-stp component skill validate --path ./playwright-checks/source --json
```

Эта команда — не [`ai-stp skill install`](../cli/skill.md). Последняя
устанавливает собственный Agent Skill CLI.

## Из нативного дерева, которое уже есть

Если компонент уже лежит в layout харнесса:

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <точный source_path из finding> --json
```

Adoption принимает только путь, который discovery уже назвал. У каталога
должен быть манифест из закрытого набора (`SKILL.md`, `AGENTS.md`,
`plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `hooks.json`, `package.json` или
`pyproject.toml`). Каталог без такого файла отклоняется.

## Сетапы

Соберите сетап из каталожных pin и embedded-источников, затем выпустите и
опубликуйте граф как набор. JSON-манифест и путь обновления — на странице
[Сетапы](../setups/index.md). Путь confirm — на
[Публикации](index.md).

## Продуктовые статьи — не пользовательская CMS

Статьи help-центра, changelog и заметки о выпуске живут в репозитории в
`docs-user-facing/content/` как Git-native Markdown, по файлу на локаль, с
совпадающими `type` и `slug`. Это не CMS, которую аккаунт редактирует с
сайта, и не способ публиковать компонент или сетап. Публикация компонента и
сетапа — CLI-путь выше.
