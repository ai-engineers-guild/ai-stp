---
description: "Проверяемая инвентаризация реальных байтов и паспортов первопартийного корпуса запуска."
last_verified: "2026-08-28"
---

# Первопартийный корпус запуска

Нормативный состав каталога принадлежит
[ADR-0034](../adr/ADR-0034-first-party-launch-corpus.md), а выпускной барьер —
[release-evidence.md](release-evidence.md). Здесь хранится проверяемая
инвентаризация уже подготовленных объектов, без изменения требуемого состава.

## Первая волна

> **Провенанс устарел, и это не редактируемо.** Пять из семи харнессов ссылаются
> на репозитории `NDDev-it-com/*-app`, которые с 2026-08-25 переведены на личный
> аккаунт `rldyourmnd` и заархивированы; оба role-репозитория — тоже. Из 126
> объектов корпуса 120 называют архивный источник и 6 — живой.
>
> Ничего не ломается: артефакты встроены под `v1/` и ни публикация, ни установка
> за ними в сеть не ходят. Устарела организация в URL, а редирект не является
> исправлением. Исправить правкой нельзя — `source` и commit входят в
> адресуемый содержимым паспорт, а опубликованная `X.Y` неизменяема
> (`REQ-2606`). Это выпуск новых объектов из живого эстейта, и он ждёт решения
> о том, сохранять ли объём каталога.

Первый срез берёт публичные AGPL-3.0-or-later выпуски пяти провайдеров:
`nddev-claude-app` `0.2.0`, `nddev-codex-app` `0.2.0`,
`nddev-grok-build-app` `0.3.0`, `nddev-opencode-app` `0.3.0` и
`nddev-pi-app` `0.2.0`. Claude Code и Codex providers не объявляют
`plugin` допустимым component kind, поэтому их marketplace разложен по
нативным границам `skill`: три компонента Claude Code и 29 компонентов Codex.
Grok Build provider объявляет `plugin`, и его дерево остаётся одним компонентом.
OpenCode разделён по шести нативным границам `instruction`, `skill`, `agent`,
`command` и `plugin`; Pi — по четырём границам `instruction`, `skill`, `plugin`
и `setting`. Файловые поверхности сохраняют точный Git blob, каталоги — точный
Git tree; искусственная директория вокруг файла не создаётся.
Каждый setup ссылается на полный набор точными версиями и passport digest.
Локальный путь, время сборки и порядок обхода каталога не входят в байты
артефакта.

| Объект | ID | Версия | Artifact digest |
|---|---|---|---|
| Claude Code NDDev Builder setup | `setup_01KZWSHE3VWEF0NT2XVRH45AJ9` | `1.0` | `sha256:6470c214f1d09998454d9ef92cc2884bc5e6ae5667f9130306c88e31384aa5b1` |
| Codex NDDev Builder setup | `setup_01KZWSHE3VM3FQMQ48CSNA40PE` | `1.0` | `sha256:3ac27d4f1f7a64b82bb57ea2cadf4c3101109fb6e7668c5e4da04afa7a97468e` |
| Grok Build NDDev Builder plugin | `component_01KZWSHE3V0T8KVJYFEKWJV63Y` | `1.0` | `sha256:3968ae9083f13ff0bc5f45043448e08f111f8203a20eaab7542f52676f4cb195` |
| Grok Build NDDev Builder setup | `setup_01KZWSHE3V0T8KVJYFEKWJV63Z` | `1.0` | `sha256:ae4f4d74edc0d36c83a8f5479233469914ac9fa4b58c5a83d27d1918689de491` |
| OpenCode NDDev Builder setup | `setup_01KZXVZ82E0ZN6Z81PBKQWMCWQ` | `1.0` | `sha256:b749648c7c8e87a560f71654db533922aaea4b96fa4b85589efcdd247f08e7cb` |
| Pi NDDev Builder setup | `setup_01KZXVZ82E0ZN6Z81PBKQWMCWR` | `1.1` | `sha256:f5e1e905ba871078c87768e6b2d73c928e82daed90baa257dba064807e60c6de` |

Pi `1.1` несёт `managed_paths` относительно дома `~/.pi/agent` (`AGENTS.md`,
`settings.json`, `skills/…`, `extensions/…`). Опубликованная `1.0` с префиксом
`agent/` неизменяема (`REQ-2606`); новая версия — единственный допустимый
способ это исправить.

## Cursor — дополнительная инвентаризация, не барьер запуска

`ADR-0034` по-прежнему требует пять базовых сетапов. Cursor не заменяет их и не
расширяет выпускной барьер: в корпус добавлены ровно те байты, которые несёт
публичный AGPL-3.0-or-later выпуск `NDDev-OpenNetwork/cursor-setup-system`
`0.0.1` (commit `27b07f2edaea248ceb7348d1d10a7f2d2b8d64d8`). Это plugin-as-unit
плюс существующие `AGENTS.md` и `cli-config.json`. mcp и hook в этом дереве нет.
Публикацию в прод выполняет коллега.

| Объект | ID | Версия | Artifact digest |
|---|---|---|---|
| Cursor NDDev Builder instruction | `component_01M0SSJPYR4VH8R2YSHYESHK9K` | `1.0` | `sha256:fa6327804dfa4e074dfbd6ee3e48eb05ef9c5e83a470ff49cf5565a996419c62` |
| Cursor NDDev Builder setting | `component_01M0SSJPYR4VH8R2YSHYESHK9M` | `1.0` | `sha256:e04cab1805029cc1a543db6a2770846efc5ca513086fabb742b59af5d62f02d9` |
| Cursor NDDev Builder plugin | `component_01M0SSJPYR4VH8R2YSHYESHK9N` | `1.0` | `sha256:adc3ab811ecf36ea14fff467991d2ef328967b8412a8c76dd4001aaedf3e9a1c` |
| Cursor NDDev Builder setup | `setup_01M0SSJPYR4VH8R2YSHYESHK9P` | `1.0` | `sha256:0912212d9e3d44c7bbf4b361440b49a1169744f33afc5e725693955cf142f27c` |

Точное происхождение закреплено без плавающих ссылок:

| Харнесс | Source commit | Setup blob |
|---|---|---|
| Claude Code | `4082a42f4d92653ed379721b4cd08906e5059dd5` | `c2cefd0aeaba92d3bb627e3dd2072d6b365fc03b` |
| Codex | `138e876616ee16bea155d00a1589f4639c45addf` | `865839268cf62f34404659dc39ff082b25647e52` |
| Grok Build | `307e5124a1919a2224692cc8d64c50f98364ef2b` | `2acec9e28f0aaac9a6f12e92d4d14785c9aed891` |
| OpenCode | `ecb1380f56124867520700f0ccf9b05801293863` | `5fa135bc7e9423e24411dc7c2187597c1e30d4e1` |
| Pi | `2fbb9d0dff2f28076868e4f0457d7ed48aa5263f` | `5a9e00442a82589ca8b8a98a46e9f4804a3d2174` |
| Cursor | `27b07f2edaea248ceb7348d1d10a7f2d2b8d64d8` | `02ef1e0cec37b0f4be65aecfdecc510d782ca14f` |

Точные подпути, Git object SHA и стабильные ID всех компонентов принадлежат
`first_party/v1/corpus-sources.json`. Контрактный тест восстанавливает каждый
Git blob или tree SHA непосредственно из вложенных байтов и режимов файлов.

`safe` и `full-auto` остаются execution profiles одного setup graph, а не двумя
content setup. Переключение профиля не меняет component, setup artifact или
граф по `SPEC-008` `REQ-835`; оба профиля проверяются provider lifecycle
отдельно от корпуса содержимого.

Импортируемый владелец данных — `ai_stp_contracts.first_party`. Он поставляет
точные байты артефактов, полные запечатанные паспорта и их хэши одним набором и
используется обеими сторонами вместо независимых копий. Контрактный тест
проверяет манифест ZIP, хэш каждого элемента, точный источник, связь сетапа с
компонентом и обе адресуемые по содержимому идентичности.

## Ролевые семейства Claude Code и Codex

Второй срез использует публичные стабильные AGPL-3.0-or-later выпуски
`rldyour-claudecode` `1.8.8` и `rldyour-codex` `1.8.11`. Из них извлечены только
60 реально используемых нативных skill-деревьев. Для каждого харнесса собраны
шесть разных графов `backend`, `frontend`, `full-stack`, `code-review`,
`security` и `research`; совпадающих графов внутри одного харнесса нет.

| Харнесс | Source commit | Contract blob | Компоненты | Сетапы |
|---|---|---|---:|---:|
| Claude Code | `7c2ec4ed669ff8d2424d9e5a65f8329092b32cd7` | `a9ed3c37b617534dc91988662979dc0f1d58ddc7` | 27 | 6 |
| Codex | `1080ef355569d5be00ae5b8126860983779cfbea` | `967d182c0666ca90c0a01e91903f0358707d93d1` | 33 | 6 |

Точная роль, назначение, задачи, теги, состав графа, stable ID, source path и
Git tree SHA принадлежат `first_party/v1/role-sources.json`. Setup-композиция
принадлежит корпусу `ai_stp`, а публичный `config/rldyour-contract.json` точного
релиза является доказательством доступных upstream-доменов; поэтому паспорт не
приписывает upstream несуществующий ролевой setup-файл. Codex `code-review`
дополнительно включает шесть нативных reviewer skills своего стабильного
релиза. Контрактный тест доказывает различие графов, точность ссылок на
компоненты и восстановление Git tree SHA из каждого архива.

## Незакрытая интеграция

Все пять базовых setup локально проходят offline acquisition, сборку exact
HarnessBundle и lifecycle закреплённого public provider. Для Codex, Grok Build,
OpenCode и Pi дополнительно доказано, что `safe` и `full-auto` используют один
и тот же bundle; Claude Code release `0.2.0` не объявляет permission profiles,
поэтому клиент не приписывает ему отсутствующую возможность.

Эта волна закрывает клиентскую подготовку реальных байтов, но не выдаёт
серверную публикацию за выполненную. Маршрут привязки реальных байтов к
publication plan существует с 2026-08-16: `#312` закрыт слиянием `#366`.
Открытым остаётся то, что сервер сеет **не этот корпус**: `load_first_party_seed`
раскладывает написанный вручную набор Sprint-1, а `ai_stp_contracts.first_party.CORPUS`
не импортируется ничем в `apps/` — этим владеет `#374`. Пока это так, `#162`
остаётся открытой: совпадение CLI и web должно быть доказано на одной
опубликованной версии, а не выведено из локальной фикстуры.

Датированный provider install/status/remove/rollback trace каждого точного
ролевого setup хранится в `#186`: паспорт ссылается на эту запись, а не выдаёт
upstream release page за доказательство установки производной композиции.
Протокол v3 этих providers не объявляет отдельную launch operation; следующий
read-only process проверяет установленную поверхность через `status`.
