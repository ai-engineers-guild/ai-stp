---
description: "Версионируемые scaffold-планы и безопасная проекция authoring templates компонентов."
last_verified: "2026-08-13"
---

# Authoring templates компонентов

Переносимый синтаксис принадлежит `SPEC-005` REQ-528, а полный scaffold lifecycle —
[`SPEC-041`](../../specs/active/SPEC-041-component-scaffold-framework.md). Ни один
из путей не публикует объект и не записывает итоговое состояние харнесса.

## Команды

`component scaffold plan` принимает вид, язык, вариант харнесса, имя и новый
каталог. Он ничего не записывает и возвращает версии template/generator, полный
список файлов, размеры, режимы, digest каждого файла и digest всего плана.
Файл хешируется в домене `ai-stp:artifact:v1`, канонический JSON входов плана —
в домене `ai-stp:scaffold-plan:v1`; `plan_id` выводится из первых 24 hex-символов
plan digest.

`component scaffold apply` принимает те же входы, exact
`--expected-plan-digest` и `--confirm`. CLI повторно строит план, резервирует
новый каталог без перезаписи и создаёт файлы `0600`, откатывая собственный
неполный результат при отказе. Существующий target — даже пустой — symlink и
отсутствующий parent отклоняются; скрытой перезаписи или merge нет.

Декларативные `instruction`, `skill`, `agent`, `setting` используют
`--language none`. Исполняемые `mcp`, `hook`, `command`, `plugin` выбирают
`python`, `typescript`, `javascript`, `rust`, `go` или `dart-flutter`. Вариант —
`portable`, `claude-code`, `codex`, `pi`, `opencode` или `grok-build`.

Каталог содержит `component-passport.json`, `eval-profile.json`, descriptor,
переносимый файл authoring-template.md, README, safety declaration, publication checklist,
исходник и тест. Паспорт —
локальный patch: в нём нет придуманного source, секретов или разрешения
распространения. Автор продолжает путь через `component passport validate`,
локальную регистрацию и команды публикационного плана.

## Путь автора

1. Выполнить `component scaffold plan`, просмотреть descriptor, каждый файл и
   digest, затем передать неизменившиеся входы в `component scaffold apply` с
   exact plan digest и `--confirm`.
2. Реализовать поведение и заполнить только подтверждённые факты patch. Для
   `required_env` записываются имена и назначение, но не значения. Source
   добавляется только после фиксации публичного GitHub commit.
3. Поместить компонент в поддержанный native layout, выполнить
   `component discover` и `component adopt`, затем применить patch через
   `component passport update --expected-revision ... --from ... --confirm`.
4. Выполнить `component passport validate` и evaluation lifecycle. Сохранённый
   профиль заранее показывает, что core выполнит local-static checks, а
   model/human checks без соответствующего runner честно останутся `not_run`.
5. Записать и выпустить точную версию, после чего использовать
   `publication plan` и `publication confirm`. Publication checklist не является
   разрешением: источник, лицензия, evidence и серверная проверка остаются
   обязательными отдельными границами.

`component template render` читает один обычный файл не более 64 KiB без
перехода по symlink и возвращает проверенную проекцию в machine output. Исходный
файл и target при этом не меняются. Ответ содержит SHA-256 исходного и
полученного UTF-8 текста, чтобы повтор можно было сравнить байт-в-байт.

## Закрытый синтаксис

Вне fenced code разрешены только четыре placeholders:

```text
{{harness_id}}
{{component_name}}
{{component_root}}
{{config_root}}
```

Они означают соответственно выбранный идентификатор харнесса, ограниченный
идентификатор `lowercase slug`, переданный относительный `POSIX path` и
`config root` из исполнимого реестра харнессов.

Условный блок занимает отдельные строки:

```text
{{#harness:claude-code,codex}}
Текст только для перечисленных харнессов.
{{/harness}}
```

Имена в условии берутся только из закрытого реестра. Повторы, неизвестные
имена, вложенные, лишние и незакрытые блоки отклоняются. Внутри fenced code
placeholders и условные теги сохраняются буквально, поэтому пример синтаксиса
не исполняется как шаблон.

`component_root` не бывает абсолютным, не начинается с `~`, не содержит `..`,
`.` или обратную косую черту и ограничен 512 символами. Значения placeholders
сами проходят закрытую проверку, поэтому подстановка не может добавить новую
строку или управляющий тег.
