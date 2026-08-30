---
description: "SPEC-041: Версионируемые scaffold-планы полного authoring-каталога компонента."
last_verified: "2026-08-29"
---

# SPEC-041: Scaffold framework компонентов

## Цель

Автор или агент получает детерминированную заготовку компонента, которую можно
проверить, зарегистрировать локально и затем обогатить точным происхождением для
публикации. Создание отделено от preview точной границей plan/confirm и никогда
не перезаписывает существующий путь.

## Границы

Framework создаёт локальный authoring-каталог и закрытый паспортный patch. Он не
регистрирует объект, не придумывает public source, лицензию или полномочия, не
вызывает package manager и не выполняет сгенерированный код.

## Термины

- **Descriptor** — закрытый выбор версии template/generator, вида, языка и
  варианта харнесса.
- **Scaffold plan** — content-addressed preview всех создаваемых файлов.
- **Scaffold apply** — подтверждённое создание нового каталога по exact plan.

## Требования

- `REQ-4101`: Descriptor фиксирует версии template и generator, один из восьми
  видов компонента, язык, portable или конкретный harness variant и признак
  исполняемости.
- `REQ-4102`: Матрица допускает `none` для декларативных `instruction`, `skill`,
  `command`, `agent`, `setting`; `mcp` и `plugin` используют один из исполняемых
  языков, а `hook` — только язык, чей source можно запустить после установки без
  неявной сборки. Сочетание без нативной семантики выбранного харнесса
  отклоняется до записи файлов.
- `REQ-4103`: Plan перечисляет каждый относительный путь, точный byte length,
  режим и domain-separated digest и связывает их с абсолютным новым target.
- `REQ-4104`: Scaffold содержит descriptor, закрытый component passport patch,
  `SetupEvalProfile`, README, safety declaration, publication checklist,
  исходную заготовку и проверку для выбранного языка.
- `REQ-4105`: Passport patch использует только имена `required_env`, объявляет
  пустые минимальные permissions и capabilities и честно сохраняет
  `NOASSERTION`/запрет распространения до решения автора. Portable descriptor не
  выдаётся за паспорт конкретного харнесса.
- `REQ-4106`: Apply повторно строит plan из тех же явных входов, требует его
  exact digest и `--confirm`, создаёт owner-only файлы с откатом своего неполного результата и закрывается
  отказом для существующего target, symlink или отсутствующего parent.
- `REQ-4107`: Eval skeleton содержит локальную deterministic проверку, а
  недоступные model/human проверки при выполнении получают `not_run` по
  `SPEC-040`; scaffold сам код не исполняет.
- `REQ-4108`: Scaffold содержит каталог `native/` с точной раскладкой выбранного
  харнесса. `instruction`, `command`, `agent` и `setting` получают нативный файл
  или каталог из реестра проекций; целый settings-файл является одним
  компонентом. Codex `agent` не маскируется под отдельный вид: такая комбинация
  отклоняется.
- `REQ-4109`: `hook-source.json` строго фиксирует событие, порядок, блокирующую
  политику отказа и команду обработчика. Нативный manifest и соседний handler
  выводятся детерминированно; scaffold не создаёт заглушку `handle_event`.
- `REQ-4110`: Manifest-directory plugin несёт нативный manifest выбранного
  продукта. OpenCode plugin является одиночным `plugins/<name>.js|ts`, Pi
  extension — одиночным JS/TS package entry. Регистрация marketplace не входит
  в plugin package и моделируется отдельным `setting`.

## Состояния и ошибки

Plan не является сохранённым mutable объектом: одинаковые входы и свободный
target дают одинаковые bytes и digest. Неверная комбинация матрицы, stale plan,
изменённые bytes, занятый или небезопасный target дают типизированный отказ до
изменения принадлежащих пользователю файлов.

## Безопасность и приватность

Scaffold не читает environment values, credentials и пользовательские файлы.
Он не открывает сеть и не исполняет созданный код. Patch содержит только пустой
список `required_env`; последующее обогащение принимает имена переменных, но не
их значения. Cleanup удаляет только файлы и каталоги, созданные текущим apply.

## Совместимость и миграция

`component-scaffold/2` и `ai-stp/2` являются текущими независимыми версиями
template и generator; descriptors версии `1` остаются валидными. Изменение точных создаваемых байтов требует новой template version;
изменение механики без изменения descriptor contract требует новой generator
version. Старые descriptors остаются валидируемыми собственной схемой.

## Критерии приёмки

| Требование | Исполнимый способ проверки |
|---|---|
| `REQ-4101` | Строгая схема отклоняет неизвестные поля и значения вне закрытых vocabulary. |
| `REQ-4102` | Параметризованный тест проходит всю type × language × variant матрицу и отрицательные сочетания. |
| `REQ-4103` | Повторный preview совпадает, а каждый digest пересчитывается из фактических bytes. |
| `REQ-4104` | Для каждой строки матрицы паспорт и eval profile проходят свои схемы, а обязательные файлы присутствуют. |
| `REQ-4105` | Fixtures не содержат secret values, public source claim и разрешение распространения. |
| `REQ-4106` | Без confirm, со stale digest, существующим target, symlink и отсутствующим parent операция отказана без изменения файлов. |
| `REQ-4107` | Eval profile содержит deterministic и model-assisted checks; общий runner подтверждает честный `not_run`. |
| `REQ-4108` | Fixtures нативных instruction/command/agent/setting совпадают с реестром; неподдерживаемый Codex agent отказан без записи. |
| `REQ-4109` | Hook fixtures сохраняют событие, порядок, failure policy и команду; malformed source отклоняется строгой схемой. |
| `REQ-4110` | Fixtures различают manifest packages и одиночные OpenCode/Pi modules; plugin не пишет marketplace settings. |
