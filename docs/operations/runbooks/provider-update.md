---
description: "Runbook: provider update."
last_verified: "2026-08-03"
---

# Обновление провайдера

## Подготовка подписанного выпуска

После получения byte-identical candidate от закрытого release harness ключ
издателя создаётся и хранится только вне checkout. Команда выводит public key и
детерминированный `key_id`, которые затем отдельно закрепляются в consumer policy:

```bash
python apps/cli/tools/provider_release.py keygen \
  --private-key /secure/ai-stp/provider-release-ed25519.pem
```

Манифест подписывает точный executable, commit, URL, platform profile и
монотонную sequence. Для текущего release profile указываются только фактически
доказанные `linux` и `x86_64`; переносимые code paths не являются macOS evidence:

```bash
python apps/cli/tools/provider_release.py sign \
  --private-key /secure/ai-stp/provider-release-ed25519.pem \
  --provider-id nddev-claude-app \
  --provider-version 0.2.0 \
  --repository github.com/NDDev-it-com/nddev-claude-app \
  --commit <exact-commit> \
  --license AGPL-3.0-or-later \
  --artifact /secure/candidates/nddev-claude-app-0.2.0 \
  --artifact-url https://github.com/NDDev-it-com/nddev-claude-app/releases/download/0.2.0/nddev-claude-app-0.2.0 \
  --entry-point nddev-claude-app-0.2.0 \
  --protocol-version 3 \
  --sequence 1 \
  --supported-os linux \
  --supported-arch x86_64 \
  --output /secure/candidates/nddev-claude-app-0.2.0.manifest.json
```

Перед публикацией `verify` повторно читает точные байты артефакта и применяет
тот же договор доверия потребителя. Закрытый ключ, байты кандидата и
промежуточные манифесты не коммитятся; в репозиторий попадают только открытый
ключ и точные дайджесты опубликованных артефактов после неизменяемой публикации.

## Подготовка выпуска

1. Зафиксировать публичный репозиторий, коммит, версию протокола и связанный issue.
2. Выполнить публичные проверки и закрытый барьер `nddev-harnesses`.
3. Собрать воспроизводимый артефакт и манифест с хэшем, размером и последовательностью.
4. Подписать выпуск разрешённым ключом или издателем по текущей политике доверия.
5. Получить Linux x86_64 evidence для выбранной release line. macOS evidence нужно
   только перед будущим добавлением macOS в support matrix по `ADR-0062`.
6. Для protocol v2 на каждой ОС выполнить capability probe. `enforced` принимается
   только вместе с launcher identity, SHA/version и положительным контролем
   DNS-UDP/IPv4/IPv6; `unavailable` блокирует локальную фазу до запуска provider.

## Продвижение

1. Отдельно продвинуть закреплённую версию в `nddev-harnesses`.
2. Отдельным PR обновить манифест потребителя в `ai_stp`.
3. Проверить источник, подпись, хэш, защиту от отката, платформу и `provider-info`.
4. Установить новую версию рядом со старой и выполнить диагностику и контрактные проверки.
5. Атомарно переключить текущий указатель. Пользовательские цели не обновляются автоматически.

## Проверка после переключения

1. Повторно получить `provider-info`, проверить действия и версию.
2. Выполнить безопасный план на тестовой цели, затем состояние и восстановление.
3. Записать точный артефакт, команды, результаты и пропущенные платформы.
4. Записать `network_requirement`, фактический `network_enforcement` и evidence для
   каждой выполненной фазы. Linux/Bubblewrap evidence не доказывает macOS; без
   отдельного real-host evidence macOS остаётся `not_verified`.

## Возврат

При ошибке вернуть указатель на прошлую установленную проверенную версию. Не использовать `latest` и не загружать новый артефакт во время возврата. Если выпуск отозван, заблокировать новые установки и опубликовать список затронутых версий и инструкцию восстановления.
