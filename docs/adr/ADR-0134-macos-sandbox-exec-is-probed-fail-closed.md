---
description: "Решение использовать системный sandbox-exec на macOS только после нативной пробы запрета сети и без fallback на trust exception."
last_verified: "2026-08-31"
---

# ADR-0134: macOS sandbox-exec проверяется и закрывается отказом

Статус: принято. Снимает долг `ADR-0126` для macOS.

## Контекст

На Linux consumer доказывает Bubblewrap, на Windows — AppContainer. macOS до
этого разрешал локальную фазу доверенного выпуска без сетевой изоляции. В
актуальной macOS остаётся системный `/usr/bin/sandbox-exec`; профиль Seatbelt
может запретить сеть непривилегированному process tree, но сам интерфейс и язык
SBPL являются deprecated/private surface.

Наличие executable поэтому не является доказательством capability. Нельзя
переносить наблюдение с одной версии macOS на другую и нельзя называть запуск
`enforced`, пока тот же host не прошёл положительный и отрицательный контроль.

## Решение

Consumer использует только системный `/usr/bin/sandbox-exec`, если executable и
все его предки принадлежат `root` и не доступны на запись группе или остальным.
Закрытый профиль разрешает существующую файловую/process поверхность и
запрещает `network*`:

```scheme
(version 1)
(allow default)
(deny network*)
```

Перед первым provider spawn consumer доказывает на текущей машине:

1. родитель без sandbox достигает локальных IPv4, IPv6 и DNS-like UDP controls;
2. тот же Python child и те же endpoints под профилем не достигаются;
3. executable имеет точный SHA-256, записанный в evidence.

Только полный результат становится `network_enforcement=enforced` и
`v3_local_phase=network_denied`. Отсутствие executable, недоверенный путь,
ошибка SBPL или неоднозначная проба остаются `unavailable`; локальная v3-фаза
отказывается до provider spawn. macOS удалён из `UNISOLATED_PLATFORMS`, поэтому
`trusted_release` и `explicit_unverified_provider` больше не обходят отказ.

## Последствия

- deprecated/private surface не превращается в постоянное обещание: capability
  измеряется при каждом процессе consumer и может честно стать `unavailable`;
- fallback не подменяет отсутствие механизма доверием к provider bytes;
- профиль ограничивает только сеть. Владение target, exact argv, environment,
  timeout и output bounds остаются в существующем provider contract;
- нативная macOS матрица является обязательным evidence. Linux или мок не
  доказывают, что текущая macOS принимает профиль и блокирует transport.

## Условия пересмотра

Решение заменяется, когда macOS публикует поддерживаемый arbitrary-process
sandbox API с не меньшим fail-closed свойством или удаляет `sandbox-exec`/SBPL.
В обоих случаях consumer сначала добавляет нативную пробу нового механизма, а
не переносит `enforced` по имени API.
