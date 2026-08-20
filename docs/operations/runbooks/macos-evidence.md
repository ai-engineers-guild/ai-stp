---
description: "Получение CLI/package evidence на стандартном GitHub-hosted macOS runner."
last_verified: "2026-08-18"
---

# Будущее доказательство CLI на macOS

## Граница

По `ADR-0062` macOS не входит в текущую support matrix и не блокирует текущий
Linux x86_64 release profile. Workflow `macos-evidence.yml` сохраняется как честный
future portability gate и подтверждает только CLI/package часть: Python 3.12 и
3.14, статические проверки, SQLite/local tests, cross-platform HarnessBundle oracle,
wheel, `uv tool`, Agent Skill, exact five-wheel release candidate и сохранение
локальных данных после uninstall. Каждая строка matrix получает отдельный
`UV_PROJECT_ENVIRONMENT` в `RUNNER_TEMP` и сверяет фактическую версию Python внутри
установленного CLI; старое окружение persistent runner не может подменить matrix.

Он не закрывает Claude Code/Codex provider E2E, protocol v2 network enforcement или
публикацию PyPI. Эти доказательства требуют точных подписанных provider releases и
отдельного разрешения на выпуск по `release-evidence.md`.

## Предпосылки

1. Использовать только стандартный GitHub-hosted `macos-15`; отдельный постоянный
   self-hosted macOS runner не регистрируется.
2. Не предоставлять задаче маршрут SSH для развёртывания, идентификацию PyPI или
   постоянные секреты.
3. Python и `uv` устанавливает workflow поверх стандартного runner image.
4. Убедиться, что рабочая учётная запись не содержит нужных тесту записей Keychain.
   Workflow дополнительно устанавливает `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1`,
   поэтому regression обязан работать только внутри временного каталога.

## Запуск

Запустить вручную workflow `macos-evidence` на точном commit. Matrix выполняется
последовательно на эфемерных hosted workers для Python 3.12 и 3.14. Push, deployment и publication
workflow не выполняет.

Проверка `-m "not platform"` исключает server/PostgreSQL slice: отсутствие Docker на
macOS-машине не превращается в фиктивный platform success. Полный platform gate
остаётся на Linux; macOS run доказывает только заявленную переносимость CLI.

## Приёмка evidence

Сохранить для каждого matrix job:

- exact repository/ref/SHA и чистый checkout;
- `RUNNER_NAME`, `uname -a`, `sw_vers`, архитектуру и версию Python;
- полный результат `back-static` и число прошедших/пропущенных CLI tests;
- JUnit artifact, хэши distributions и результат установки вне checkout;
- manifest, checksums и JSON-доказательство exact five-wheel candidate, включая
  PEP 610 provenance и фактическую версию Python;
- установку/status/remove Agent Skill и сохранение registry после `uv tool uninstall`;
- literal ZIP bytes, `bundle_digest` и `artifact_digest` результата
  `test_bundle_cross_platform_golden.py`;
- все skipped/not-run причины и остаточные риски.

Этот workflow нужен до будущего добавления macOS в support matrix. Issues `#167`,
`#175` и `#176` для текущего Linux x86_64 профиля он сам по себе не закрывает и не
заменяет Linux provider E2E.

## Текущее состояние

С `2026-08-18` workflow использует `macos-15` как стандартный fallback. После
появления macOS-класса Drakkars эта единственная цель `runs-on` должна быть
заменена на имя соответствующего scale set.
