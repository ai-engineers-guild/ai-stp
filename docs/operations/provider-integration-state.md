---
description: "Публичный снимок совместимости семи provider systems и ai_stp."
last_verified: "2026-08-31"
---

# Состояние интеграции provider systems

Pins принадлежат provider policy/manifests, нормативная wire boundary —
`docs/contracts/provider-protocol.md`. Здесь перечислены только публично
проверяемые release/capability/evidence facts.

## Active release

Active public tag семи `NDDev-OpenNetwork/*-setup-system` — `0.0.48`. Каждый
release содержит шесть native binaries и `SHA256SUMS`, прочитанные обратно из
GitHub.

## Capabilities

- core configuration binary/provider-info существует на шести OS/arch строках
  у всех семи;
- software install/update/remove доступен 6/6 у всех семи систем;
- complete launch объявляют Claude Code, Codex, Grok Build, OpenCode и Pi;
  Cursor/Antigravity launch не объявляют;
- provider-kit `0.2.7` публикует closed status-response schema; consumer
  валидирует весь envelope против неё на единственной границе вызова.

## Evidence

Exact-current provider plan/digest/apply/update/rollback операции прошли 6/6 у
всех семи systems. Pi oracle сравнивает pre/post launch output, потому что оба
exact vendor releases на Windows отвечают `0.0.0` на `--version`.

Все три ОС запрещают сеть устройством: Linux — Bubblewrap, Windows —
AppContainer, macOS — системный `sandbox-exec` после нативной transport probe.
Без executable или proof локальная фаза отказывается и trust exception нет.

Filesystem boundary одинакова на всех трёх: writable только target и явно
названные вызывающим пути.

Provider implementation/release и consumer enforcement — отдельные commits и
границы изменений. Consumer enforcement schema ответа `status` выполнен;
следующий шаг — cross-repository evidence на consumer path.
