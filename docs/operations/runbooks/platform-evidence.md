---
description: "Six-leg platform evidence точного CLI candidate без publish/deploy authority."
last_verified: "2026-08-31"
---

# Platform evidence

Manual workflow `platform-evidence.yml` доказывает CLI/package и consumer
network boundary на Linux, Windows и macOS для обеих архитектур. Он не публикует
PyPI, не продвигает deploy и не заменяет setup-systems-owned provider lifecycle.

## Шесть native legs

| Runner | Native row |
|---|---|
| `ubuntu-24.04` | Linux/x86_64 |
| `ubuntu-24.04-arm` | Linux/arm64 |
| `windows-2025` | Windows/x86_64 |
| `windows-11-arm` | Windows/arm64 |
| `macos-15-intel` | macOS/x86_64 |
| `macos-15` | macOS/arm64 |

Каждая job проверяет `RUNNER_ARCH`, использует отдельное окружение, нативный
`uv`, пять точных candidate wheels и временное хранилище credentials. Эмуляция x64 на
ARM не засчитывается.

## Что выполняется

- build и install exact five-wheel CLI candidate вне checkout;
- machine commands и фактическая Python/OS/arch identity;
- portable bundle oracle и uninstall с сохранением пользовательских данных;
- `provider network` и runtime probes consumer boundary.

Linux должен доказать Bubblewrap или ранний отказ. Windows — AppContainer с
runtime proof/fail-closed. macOS отдельно записывает допустимый trust exception;
он не называется `enforced`.

## Отдельная producer evidence

Полный provider plan/apply/status/recovery/rollback принадлежит workflows семи
setup systems. Их six-leg runs связываются с теми же platform rows, но не
встраиваются в этот workflow и не получают его успех автоматически. Consumer
Итоговое evidence выпуска объединяет два точных результата после выпуска producer.

## Artifact

Сохранить repository/ref/SHA, runner image/OS/arch, Python/uv, distribution
digests, PEP 610 provenance, bundle/provider network digests и все
`not_verified` reasons. Успешное существование workflow без run на candidate
ничего не доказывает.
