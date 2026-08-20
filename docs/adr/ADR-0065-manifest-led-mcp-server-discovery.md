---
description: "Bounded обнаружение MCP server packages только по согласованной цепочке package manifest и entry point."
last_verified: "2026-08-10"
---

# ADR-0065: Manifest-led обнаружение MCP server packages

Статус: принято.

## Контекст

Файл клиентской конфигурации MCP и реализация сервера имеют один product type
`mcp`, но разные native roles. Точный `.mcp.json` уже обнаруживался как client
config, тогда как source packages серверов были невидимы. Поиск по подстроке
`mcp`, `server.py`, `hooks` или Dockerfile дал бы много application, test и docs
false positives и потребовал бы произвольного чтения проекта.

## Решение

В явно выбранном project root CLI выполняет bounded manifest-led traversal. Он
не переходит по символическим ссылкам, исключает деревья зависимостей, кэша,
сборки, документации, фикстур и тестов и ограничивает глубину, число каталогов,
число записей и размер каждого прочитанного файла метаданных или исходников.

Python candidate требует одновременно `pyproject.toml`, dependency `mcp` или
`fastmcp`, объявленный `project.scripts` entry point, существующий точный module
source и импорт MCP SDK в этом source. TypeScript candidate требует
`package.json`, официальный SDK dependency, объявленный `bin` или script source
и SDK import в точном entry file. Ничего не исполняется.

Candidate получает `component_type=mcp`, `native_role=mcp_server`, собственный
source root, entry points, доказанные `stdio`/`http` transport capabilities и
относительные evidence refs. Точный `.mcp.json` получает
`native_role=mcp_client_config`. Launcher manifest становится дополнительным
evidence только когда bounded content ссылается на уже доказанный entry point;
сам launcher не создаёт candidate.

## Последствия

- nested Python и TypeScript packages в monorepo становятся explainable;
- docs, tests, frontend hooks, Dockerfile и имя с `mcp` сами по себе не являются
  доказательством сервера;
- неизвестный transport остаётся пустым списком, а не угадывается;
- принятие пакета исходников сохраняет роль, точку входа, транспорты и ссылки
  доказательств в content-addressed локальной ревизии;
- новый ecosystem или manifest format требует отдельной fixture и обновления
  этого adapter.

## Условия пересмотра

Решение пересматривается при появлении универсального подписанного MCP package
manifest или официального cross-language discovery protocol.
