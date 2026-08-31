---
description: "Обязательные доказательства выпуска CLI, платформы и семи provider systems."
last_verified: "2026-08-31"
---

# Доказательства выпуска

Этот документ задаёт форму evidence, а не хранит текущий снимок версий. Текущее
состояние и оставшаяся работа принадлежат `implementation-roadmap.md`.

## Общая запись

Каждый выпуск связывает exact repository/ref/SHA, версию, digests артефактов,
версии schemas/policy, платформу, команды и наблюдаемые outcomes. Старый запуск
на другом CLI или provider tag не переносится. Пропущенная строка получает
`not_verified`; успешная сборка не называется real-product lifecycle.

## CLI и пять Python-пакетов

Candidate состоит из согласованных foundation, passports, assurance, contracts
и CLI. Wheel/sdist собираются повторно, сравниваются побайтово и сопровождаются
metadata, LICENSE, CycloneDX SBOM, manifest, checksums и provenance exact SHA.
Install smoke связывает все пять exact candidate wheels по PEP 610 и выполняет
machine commands вне checkout.

Native release matrix содержит:

- `ubuntu-24.04` и `ubuntu-24.04-arm`;
- `windows-2025` и `windows-11-arm`;
- `macos-15-intel` и `macos-15`.

Каждая строка использует нативный toolchain своей архитектуры, отдельное
окружение и фактическую версию Python из ответа установленного CLI. Эмуляция
другой архитектуры не закрывает строку.

## Семь provider systems

Общий core проверяется для Claude Code, Codex, Cursor, OpenCode, Antigravity,
Pi и Grok Build. Для каждой системы evidence раздельно отвечает:

1. существует ли exact provider binary на OS/arch;
2. объявлена ли конкретная operation на этой строке;
3. прошли ли plan/apply/status/recovery или ожидаемый типизированный отказ на
   exact release bytes;
4. совпадают ли provider-info, vendored provider-kit schemas и consumer policy.

Software lifecycle доступен на 6/6 строках у всех семи систем. Complete launch
имеют пять систем: Claude Code, Codex, Grok Build, OpenCode и Pi. Cursor и
Antigravity не получают фиктивный launch-success.

Network-free local phase использует consumer-controlled launcher с положительной
DNS/IPv4/IPv6 probe. macOS доказывает системный `sandbox-exec`; отсутствие или
ошибка пробы дают ранний отказ без trust exception. Сборка provider и direct
provider E2E не заменяют
consumer E2E через `ai-stp`.

## Платформа и live-контур

Platform evidence включает migrations PostgreSQL, tenant isolation, object
storage, queue idempotency, mixed API versions, audit, backup/restore и
readiness. Срезы `evidence-*` выполняются отдельно от repository gate: внешняя
среда и browser login не являются зависимостью `just check`.

Deployment evidence связывает зелёный public `check`, `deploy/prod`, pulled SHA
на host, успешные migrate/seed/content-import и только затем API/web readiness.
Late one-shot refusal не засчитывается как безопасный deploy, если старый web уже
остановлен; обязательные runtime secrets проверяются preflight до эффектов.

## Первый публичный каталог

Каталог выпуска покрывает семь харнессов и опубликованные postures, использует
живое происхождение и не переносит archived corpus под старой identity.
Доказательство перечисляет точные setup/component versions, разрешает каждую
ссылку, проверяет immutable bytes и выполняет установку. Восемь component kinds
— текущий schema vocabulary; отсутствие контента конкретного вида показывается
как content gap, а не скрывается добавлением фиктивного объекта.

## Публикация

PyPI publication — отдельная агент-управляемая операция после зелёного
кандидата через protected environment и Trusted Publishing OIDC. PR/check/deploy
не имеют publish credential. Standing release task позволяет агенту выполнить
environment approval текущим authenticated account без повторного вопроса.

Evidence считается неполным при несовпадении schema/docs, stale provider pin,
неизвестном provenance, отсутствующем recovery path или неисполненной строке
заявленной матрицы. Это состояние измерения, а не процессный запрет на дальнейшую
разработку: следующий план строится из точного недостающего результата.
