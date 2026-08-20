---
description: "Linux x86_64 как текущий обязательный release-evidence profile без неподтверждённой macOS support claim."
last_verified: "2026-08-09"
---

# ADR-0062: Linux-first release evidence

Статус: принято.

## Контекст

Ранние критерии MVP одновременно называли Ubuntu и macOS обязательными. Реальная
система разработки, CI, provider isolation и release rehearsal построены на Linux
x86_64. Owned macOS runner не активирован, а перенос Linux Bubblewrap boundary на
Darwin не спроектирован. Сохранение macOS как release blocker не добавляет
безопасности текущему продукту: оно либо бессрочно блокирует доказанный Linux
выпуск, либо подталкивает назвать непроведённую проверку успехом.

Владелец продукта явно выбрал не считать macOS частью текущей реализации и
release gate. При этом удаление всех переносимых code paths тоже было бы неверно:
они полезны для будущей отдельной линии и должны честно оставаться `not_verified`.

## Варианты

1. Сохранить Ubuntu и macOS обязательными. Отвергнуто: macOS infrastructure и
   network-enforcement capability отсутствуют и не являются текущим приоритетом.
2. Объявить macOS поддержанной по unit fixtures. Отвергнуто: fixture не является
   install/provider evidence на реальной OS.
3. Сделать Linux x86_64 единственным текущим release profile, а macOS оставить
   отдельной не блокирующей portability line. Выбрано.

## Решение

Текущий обязательный profile первого выпуска — Linux x86_64. CLI candidate,
HarnessBundle oracle и все пять provider lifecycle проходят на этой платформе.
Claude Code и Codex блокируют основной выпуск своим Linux evidence; Pi, OpenCode и
Grok Build выпускаются и проверяются тем же безопасным lifecycle, сохраняя beta
label по продуктовому контракту.

macOS не входит в текущую support matrix, не блокирует issues `#167`, `#170`–`#176`,
`#184`, `#185` и первый MVP release. До отдельного real-host run она называется
только `not_verified`; package classifiers, README и release metadata не должны
утверждать проверенную macOS support.

Переносимый код, Darwin refusal и ручной `macos-evidence.yml` сохраняются как
необязательный будущий oracle. Отсутствие network enforcement на macOS продолжает
закрыто отказывать для действия, требующего `network_requirement=none`; решение
не разрешает небезопасный fallback и не ослабляет provider boundary.

## Последствия

- обязательные release records фиксируют Linux distribution, kernel, architecture,
  Python и provider runtime;
- cross-platform deterministic design остаётся инвариантом формата, но закрытие
  текущей задачи требует literal повторяемости на заявленной release platform;
- workflow для macOS не является обязательной проверкой и не получает полномочий
  выпуска;
- добавление macOS в support matrix требует отдельного evidence release, а не
  изменения существующего Linux результата задним числом.

## Условия пересмотра

Решение пересматривается, когда владелец выделит macOS как поддерживаемую платформу,
появится owned runner и будет доказан полный wheel/Skill/bundle/provider lifecycle
вместе с honest network enforcement-or-refusal report.
