---
description: "Машинный контракт read-only обнаружения нативных компонентов поддерживаемых харнессов."
last_verified: "2026-08-22"
---

# Обнаружение нативных компонентов

## Граница

Владелец требований — `SPEC-005` REQ-517 и REQ-518, решения — `ADR-0054`,
`ADR-0055` и `ADR-0056`.
`component discover` проверяет только объявленные глобальные layout поддерживаемых
харнессов и layout внутри явно переданного `--root`. Команда не обходит home,
не читает значения в найденных файлах, не создаёт паспорт и не открывает
registry для записи. Отдельный adapter по `ADR-0055` читает только объявленные,
ограниченные по размеру metadata manifests, чтобы доказать package provenance;
произвольные настройки и значения секретов он не читает.
Адаптер MCP source дополнительно читает только bounded package manifest и точный
declared entry source по `ADR-0065`; он не запускает package, launcher или Git.
Адаптер клиентских MCP по `ADR-0106` открывает только тот файл, чья раскладка
объявила ключ, и читает под этим ключом только имена серверов. Объявленный путь
всё равно принадлежит чужой машине, поэтому граница «объявленный файл» держится
не на имени: symlink и файл со второй жёсткой ссылкой не читаются вовсе,
дескриптор сверяется с тем `lstat`, который его разрешил, а число серверов и
длина имени ограничены — имена уходят в `evidence_refs`, и неограниченное имя
означало бы произвольный текст там. Ограничена длина, а не набор символов:
`say "hi"` — это имя, которое кто-то выбрал, и отказ от него сообщил бы, что
файл не объявляет серверов, тогда как он объявляет.
Внешние metadata ports по `SPEC-005` REQ-529 читают только `nori.json` в явно
названном корне и `.agents/.skill-lock.json` версии 3 в проектной или глобальной
области. Они уточняют уже найденный путь или добавляют объявленный Nori component,
но не делают внешний manifest источником подтверждённых паспортных фактов.

Поддерживаемый набор — Claude Code, Codex, Pi, OpenCode и Grok Build. Общие
`.agents/skills` не принадлежат одному из них и возвращаются с `harness_id=null`.
Один физический путь не дублируется под несколькими harness только из-за
совместимости форматов.

Исполнимый владелец набора — декларативная таблица, которую показывает
`toolchain harness-capabilities`. Из неё строятся detector и discovery rules;
строка `undefined` владеет только переносимыми соглашениями без единственного
харнесса. Каждая строка называет уровень поддержки, глобальные и проектные
layout, проекционные возможности, источники и известные пробелы.

## Матрица bounded layouts

| Harness | Global | Project | Manifest-backed plugin |
|---|---|---|---|
| Claude Code | instruction, skill, agent, command, setting, MCP, plugin | instruction, skill, agent, command, setting, MCP, plugin | installed ledger/cache adapter; plugin root, skill, agent, command, hooks-directory и MCP client config |
| Codex | instruction, command/prompt, setting, shared skill | instruction, setting, agent, hook, shared skill | plugin root, skill и hooks-directory |
| Pi | instruction, skill, plugin, command, setting | skill, plugin, command, setting | не объявлен отдельный project-plugin manifest |
| OpenCode | skill, agent, command, plugin, setting | skill, agent, command, plugin, setting | bounded native plugin directory |
| Grok Build | skill, plugin, hook, setting, shared command | skill, plugin, hook, setting | bounded native plugin directory |

MCP server package не принадлежит одному harness и показывается отдельно с
`harness_id=null`. Python требует согласованную цепочку `pyproject.toml` → MCP SDK
dependency → `project.scripts` → exact module import. TypeScript требует
`package.json` → SDK dependency → `bin`/script source → exact SDK import.

`unsupported` в этой матрице не превращается в эвристику по имени файла. Новый
layout появляется только вместе с официальным источником и fixture. Поэтому
обычный `src/hooks/useFoo.ts`, business webhook и произвольный каталог `plugins/`
не становятся harness components.

Claude Code project plugin pack распознаётся так же, как Codex, и отличается
именем манифеста. Каталог под `plugins/` становится plugin только по точному
`.claude-plugin/plugin.json`; внутри доказанного plugin читаются `skills`
(каталог с `SKILL.md`), `agents`, `commands`, `hooks/hooks.json` и `.mcp.json`.

`.mcp.json` внутри plugin — это client config, а не сервер: находка получает
`component_type=mcp` и `native_role=mcp_client_config`. Такой файл доказывает
себя именем, поэтому обнаружение его не открывает и ни токен, ни URL с
встроенным доступом, ни тело `.env` в выдачу не попадают. Раскладка объявлена по
наблюдению, а не по догадке: работающие серверы лежат именно там, тогда как
`~/.claude.json`, `~/.claude/settings.json` и `~/.claude/.mcp.json` ключа MCP не
несут.

Codex, OpenCode и Grok Build держат клиентские серверы внутри файла, который
объявлен также как `setting`: у первого и третьего это `config.toml`, у второго
`opencode.json` или `opencode.jsonc`. Здесь существование файла не доказывает
ничего — он есть на любой машине, где харнесс запускали хотя бы раз, а пустое
объявление означает отказ от серверов. Поэтому такая раскладка объявляет ключ, и
файл становится находкой `mcp` только тогда, когда под этим ключом объявлен хотя
бы один сервер. Находка `setting` при этом сохраняется: один файл даёт две
находки разных видов.

Читаются только имена серверов, и они же попадают в `evidence_refs` — например
`mcp_servers.github`. Значения рядом с именем — команда, аргументы, URL,
заголовки и окружение — не читаются и не возвращаются, поэтому токен, записанный
в серверную запись, не попадает ни в паспорт, ни в лог, ни в fixture. Файл,
который не разбирается своим форматом, превышает предел размера или не несёт
ключа, находок не даёт: догадка о его содержимом была бы той самой эвристикой,
которую этот контракт запрещает.

У Pi объявленной клиентской раскладки нет. Файлы `mcp.json` под его корнем
встречаются, но их создаёт пользовательское расширение, а не сам харнесс, и
наблюдаемые экземпляры расходятся в ключе. Оглавление документации Pi страницы
про MCP не содержит, поэтому машинная таблица сообщает проверенный пробел
`no_documented_mcp_client_config`, а не выдуманную раскладку.

Это отдельный layout, а не переименование глобального адаптера кэша. Адаптер
по-прежнему читает установленный ledger, а pack — это исходное дерево
маркетплейса, в котором каталога `.claude/` может не быть совсем.

Каталог `plugins/`, ни один член которого не несёт манифеста **ни одного** из
поддержанных харнессов, не даёт компонентов и сообщает `unsupported_manifest`
один раз на коллекцию. Молчание здесь было бы хуже отказа: оператор получал бы
пустой инвентарь без причины. Пакет одного харнесса при этом не вызывает жалобы
у другого: Codex-пакет остаётся пакетом, даже не неся манифеста Claude.

Codex project hooks распознаются только как `.codex/hooks.json` или как
`hooks/hooks.json` внутри plugin, доказанного точным
`.codex-plugin/plugin.json`. Plugin hook-directory является одним компонентом и
включает manifest и его соседние scripts в детерминированный artifact; скрипты
не запускаются при discovery. Custom agents берутся только из `.codex/agents`.
Файл CODEX.md не является документированным instruction layout и возвращается как
безопасная `unsupported_manifest` диагностика с предложением использовать
`AGENTS.md`, а не как ложная нативная находка.

## Поля находки

- `candidate_id` — `sha256:` доменного хэша в
  `ai-stp:native-discovery:v1`; он адресует результат discovery, но не заменяет
  логический идентификатор принятого Component;
- `component_type` — значение закрытого словаря из восьми видов;
- `native_role` — `mcp_client_config` или `mcp_server` для MCP, иначе `null`;
- `harness_id` — владелец нативного layout или `null` для общей конвенции;
- `scope` — `global` или `project`;
- `source_path` — путь с заменой home на `~`;
- `layout_source` — официальный документ, объявляющий проверенный layout;
- `provenance` — согласованное происхождение: `filesystem/local` содержит только
  layout evidence, `package/observed` — только наблюдаемую package identity без
  remote claim, а `github/exact` требует канонический repository и полный commit
  SHA и может содержать subpath и package name/version; askill-compatible lock
  может добавить `digest` точной папки в `package/observed`, но этот digest не
  является Git commit;
- `byte_length` — размер обычного файла или `null` для каталога и неизмеримого
  entry;
- `holds_secret` — результат проверки имени, а не содержимого;
- `entry_points`, `transport_capabilities`, `evidence_refs` — только
  allowlisted структурные факты manifest-led adapter; transport может быть
  пустым, если его нельзя доказать как `stdio` или `http`;
- `reason` — безопасное основание классификации или неизмеримости.

Идентичность кандидата вычисляется из вида, harness, области, отредактированного
пути, `layout_source` и allowlisted provenance. Повтор на неизменном filesystem
возвращает те же значения в том же порядке. Изменение официального layout-source
или exact source намеренно меняет идентичность и требует повторной оценки агентом.

## GitHub provenance

Глобальные Claude plugins читаются через поддерживаемую цепочку ledger версии 2,
реестра marketplaces и marketplace manifest. Install path принимается только
внутри вычисленного plugin cache; записанный manifest-путь marketplace игнорируется.
Допускаются относительный source внутри GitHub marketplace и GitHub-backed
`github`, `url`, `git-subdir` с exact revision. Credentialed URL, путь с `..`,
неполный SHA, неизвестная версия ledger и выход из cache root закрываются отказом.

Проблема одного source adapter не удаляет независимые находки. Она появляется в
`diagnostics` с закрытым code и безопасным reason без содержимого manifest,
credential и системного текста ошибки. Наличие `github/exact` не означает
подтверждение платформой или безопасность plugin.

Установленный plugin с npm, archive, local или неполным Git evidence не исчезает:
он возвращается как `package/observed`. Агент может использовать это для
инвентаризации, но не называет repository или revision точными.

Глобальные Pi Git packages обнаруживаются только в документированном
`git/<host>/<owner>/<repository>` внутри config root. Для `github.com` adapter
читает bounded `HEAD`, loose ref или `packed-refs`; `settings.json`, Git config,
hooks, рабочие файлы и сеть не читаются и не запускаются. Такой checkout получает
`github/exact`, но enabled state и чистота рабочего дерева не угадываются.
Не-GitHub host остаётся без GitHub claim.

Grok `plugins/marketplaces` является служебным контейнером, а не plugin, поэтому
не выдаётся кандидатом. Публичный контракт Grok пока не раскрывает достаточную
структуру реестра установки для точного происхождения каждого marketplace plugin;
CLI показывает только доказуемые элементы локального layout и не угадывает источник.

## Внешние metadata ports

Nori port принимает bounded UTF-8 JSON с уникальными ключами и обязательными
`name` и `version`. Он сопоставляет только объявленные `skills`, `subagents` и
`slashcommands` с существующим реальным путём внутри названного корня. Значения
`repository`, dependencies и scripts не создают exact provenance и не
исполняются.

Skill-lock port принимает только версию 3 и существующий
`.agents/skills/<sanitized-name>`. `skillFolderHash` сохраняется как `sha1:` или
`sha256:` в наблюдаемом provenance; `source`, `sourceType` и `sourceUrl` не
доказывают repository или commit. В принятом draft остаются ссылка на lock,
folder digest и отдельный content digest фактически прочитанных байтов. Поэтому
паспортная проверка продолжает показывать отсутствие exact public source до
явного обогащения владельцем.

Оба manifest ограничены 1 MiB и 500 записями, не читаются через symlink, не
принимают duplicate JSON keys и не запускают внешние команды, scripts, Git или
package manager. Ошибка одного port возвращается безопасной диагностикой и не
удаляет независимые находки.

## Корни

Config root берётся из той же таблицы detector, что и `harness survey`.
Документированная переменная переноса целиком заменяет исходный корень. Общий home layout
разрешён только правилом без `harness_id`; неизвестный root или правило без
источника делает doctor-check `component_layouts` неуспешным.

## Действие агента

Агент группирует находки по scope и harness, показывает `layout_source` при
сомнении в классификации, отдельно показывает diagnostics и сохраняет
`candidate_id` при обсуждении выбора. GitHub origin агент называет точным только
при `provenance.kind=github` и `state=exact`; имя cache-каталога доказательством
не является.
Discovery не является согласием. До `component adopt` агент обязан получить
решение пользователя и передать точный `source_path` вместе с правильным project
root, если находка проектная.

## Внешняя идентичность источника

`component source parse` принимает published slug, GitHub shorthand или HTTPS URL,
local path и collection URL и возвращает только структурированное намерение. Этот
результат не является provenance evidence и всегда содержит
`provenance_proven=false`. Команда не открывает сеть, Git, manifest или registry.

`component source resolve` является отдельной механической границей: только
GitHub intent вместе с полным lowercase commit SHA становится `github/exact`.
Ветка, тег, короткий SHA, credentialed URL, control characters, абсолютный или
выходящий через `..` subpath закрыто отклоняются. Даже exact identity ещё не
доказывает digest и размер содержимого: эти факты получает последующий bounded
import/adopt path.
