---
description: "Публичный снимок совместимости семи provider systems и ai_stp."
last_verified: "2026-08-31"
---

# Состояние интеграции provider systems

Pins принадлежат provider policy/manifests, нормативная wire boundary —
`docs/contracts/provider-protocol.md`. Здесь перечислены только публично
проверяемые release/capability/evidence facts.

## Active release

Active public tag семи `NDDev-OpenNetwork/*-setup-system` — `0.0.47`. Каждый
release содержит шесть native binaries и `SHA256SUMS`, прочитанные обратно из
GitHub.

## Capabilities

- core configuration binary/provider-info существует на шести OS/arch строках
  у всех семи;
- software install/update/remove доступен 6/6 у Claude Code, Codex, Cursor,
  Grok Build, OpenCode и Pi; Antigravity — Linux/macOS 4/6, Windows обязан дать
  `unsupported_platform` до эффекта;
- complete launch объявляют Claude Code, Codex, Grok Build, OpenCode и Pi;
  Cursor/Antigravity launch не объявляют;
- provider-kit `0.2.7` публикует closed status-response schema. Producer release
  с vendored schema предшествует включению consumer enforcement.

## Evidence

Exact-current provider plan/digest/apply/update/rollback операции прошли 6/6 у
всех семи systems. Общий Pi workflow verdict имеет четыре green legs и две
Windows instrumentation-oracle failures: оба exact vendor releases отвечают
`0.0.0` на `--version`. PR232 сравнивает pre/post launch output; corrected
released run ещё pending.

Linux использует доказанный Bubblewrap, Windows — AppContainer runtime proof.
macOS использует системный `sandbox-exec` только после нативной transport probe;
без executable или proof локальная фаза отказывается и trust exception нет.

Provider implementation/release и consumer enforcement — отдельные commits и
границы изменений. Порядок schema ответа `status` уже дошёл до выпуска producer;
следующий шаг — consumer enforcement и cross-repository evidence.
