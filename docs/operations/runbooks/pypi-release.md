---
description: "Выпуск пяти exact Python-пакетов через Trusted Publishing."
last_verified: "2026-08-31"
---

# Выпуск PyPI

Текущую опубликованную версию читают из PyPI перед выпуском; runbook её не
копирует. Evidence contract принадлежит `docs/engineering/release-evidence.md`.

## Candidate

1. Пять `project.version` и внутренних pins совпадают.
2. `release-candidate.yml` строит exact clean tag `v<version>`.
3. Два build pass дают одинаковые wheel/sdist bytes, metadata/LICENSE,
   SBOM/checksums/provenance.
4. Install smoke вне checkout передаёт все пять wheels direct sources, проверяет
   PEP 610 и machine commands.
5. Версия отсутствует в PyPI: опубликованное имя/bytes неизменяемы.

## Publication

`publish-pypi.yml` публикует по одному package: foundation → passports →
assurance → contracts → CLI. Environment — `pypi` для foundation и
`pypi-{package}` для остальных. Checkout отсутствует; job получает только
candidate artifact и `id-token: write`, публикация использует Trusted Publishing
OIDC. Password/API token не создаётся.

Порученная задача выпуска позволяет агенту выполнить required environment approval
текущим authenticated account. Это исполнение уже порученного выпуска, а не
новый вопрос владельцу.

## Проверка

После каждого package прочитать PyPI JSON и оба distributions. После пятого —
установить `ai-stp-cli` без локального cache/index в чистый tool home, проверить
фактические версии всех пяти packages, `version`, `doctor`, `help --agent`, затем
uninstall. Зелёный workflow без чтения PyPI обратно публикацию не доказывает.

## Recovery

- отказ до upload: исправить и повторить package job;
- частичный набор: продолжить с первого отсутствующего package, не переиздавая
  готовые;
- version/bytes conflict: следующая согласованная версия;
- недоступен environment approval: исправить authenticated account/policy, не
  вводить token fallback;
- resolver взял другой source: direct wheels + PEP 610 всех пяти.

Итоговый отчёт содержит точный public SHA, workflow runs, версии/digests PyPI,
install smoke и незакрытые platform/provider evidence.
