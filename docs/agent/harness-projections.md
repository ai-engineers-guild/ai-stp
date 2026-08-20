---
description: "Различия native Agent Skill projections пяти харнессов."
last_verified: "2026-08-03"
---

# Проекции по харнессам

| Харнесс | Проекция |
|---|---|
| Claude Code | Plugin/Skill и явный import через `CLAUDE.md` в управляющем слое |
| Codex | Plugin/Skill и совместимая инструкция `AGENTS.md` |
| Pi | Package, resources, Skill и локальные settings target |
| OpenCode | Native Skill, plugin, agent и command |
| Grok Build | Native marketplace, plugin и Skill |

Нативная витрина в этой таблице является формой поставки, а не видом компонента: в таксономии каталога она выражается значением `projection_kind` по `ADR-0015`.

Одна каноническая процедура не копируется вручную. Проекция сохраняет семантику или сообщает потерю. Runtime capability подтверждается отдельно для точной версии харнесса.
