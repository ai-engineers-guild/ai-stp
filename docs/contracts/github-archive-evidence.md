---
description: "Машинный контракт локального GitHub archive evidence и истории наблюдений."
last_verified: "2026-08-15"
---

# GitHub archive evidence

## Команды

`component source evidence refresh --id <stable_id> --version <X.Y>` получает
одно официальное наблюдение. `show` и `history` читают только локальный registry.
Точные параметры и result schemas принадлежат генерируемому `help --agent`.

## Identity и состояние

Входная coordinate берётся из immutable паспорта указанной версии. Первое
наблюдение обращается по `owner/repository`, последующие — по immutable GitHub
repository id; поэтому rename и transfer меняют `repository_full_name`, но не
identity. Каждая строка содержит исходный source, точный passport digest,
`archived`, время получения, срок свежести и attribution официального REST
контракта.

`archived=true` даёт только `proposal=deprecated`. `blocked`, изменение lifecycle,
replacement, update и удаление target не являются эффектами этих команд.

## Freshness и отказ

TTL равен 24 часам. Последнее наблюдение возвращается как `fresh` или `stale`;
если его нет — как `unavailable`. Conditional `304` создаёт новое датированное
наблюдение с тем же состоянием. История append-only, поэтому последующий
unarchive не стирает прежний факт.

Ответ ограничен одним MiB и закрытой allowlist-моделью. Redirect не выполняется,
credential surface отсутствует. 403, 404, 429, server/transport failure,
неверный JSON, private repository и смена repository id закрываются отказом и
не заменяют последний хороший снимок.

## Server и public catalog

Локальный CLI evidence остаётся владельцем этого документа. Server/Web
доставка periodic archive observation снята: public catalog больше не несёт
`github_archive`, а detail читает on-demand `stars`/`archived` по `SPEC-049`
и `ADR-0096`.
