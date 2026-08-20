---
description: "Машинная форма полного discovery проектов в явно названной области."
last_verified: "2026-08-09"
---

# Discovery проектов

Владелец требований — `SPEC-004`, решение обхода — `ADR-0053`.

`project discover --root <path> --json` является read-командой. Она не создаёт
registry, Project или паспорт и возвращает:

- `discovery_root` — явно выбранная область с редактированным home prefix;
- `complete` — доказательство, что ни access error, ни entry limit не оборвали обход;
- `candidates` — детерминированно отсортированные уникальные корни;
- `diagnostics` — наблюдаемые причины каждого пропуска.

Candidate содержит `root`, `kind`, `state`, `markers` и `reason`. `kind` принимает
`project` и `nested_repository`; `state` — `new` и `established`; marker `git`
покрывает как каталог `.git`, так и worktree-файл `.git`. Manifest package внутри
monorepo не создаёт Project, но отдельный Git marker всегда показывается.

Diagnostic содержит редактированный `path`, закрытый `code` и безопасный `reason`:

| Code | Смысл | Влияет на `complete` |
|---|---|---|
| `excluded` | каталог исключён политикой vendor/VCS/cache/build | нет |
| `symlink` | symlink не пройден | нет |
| `entry_limit` | каталог содержит больше разрешённого числа записей | да |
| `unreadable` | каталог или путь невозможно проверить | да |

`complete=false` запрещает агенту называть список исчерпывающим. Агент показывает
diagnostics и предлагает сузить root или исправить доступ, затем повторяет read.
Ни один diagnostic не разрешает автоматически зарегистрировать найденный root.
