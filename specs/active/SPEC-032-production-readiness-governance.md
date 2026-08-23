---
description: "SPEC-032: Доказательная готовность production, governance данных, защита от злоупотреблений и восстановление."
last_verified: "2026-08-22"
---

# SPEC-032: Готовность production, governance и восстановление

## Цель

Перед первым production release платформа доказывает на точном commit, что её
конфигурация, наблюдаемость, обработка данных, защита от злоупотреблений и
восстановление готовы к эксплуатации. Это доказательство не выполняет изменение
production само и не заменяет явное решение владельца.

## Границы

Входят проверка production-конфигурации, безопасные доказательства выпуска, SLO и
политика оповещений, проверяемое управление данными, серверная защита от
злоупотреблений, резервные копии, тренировки восстановления и отката, документация
оператора и доказательства выпуска. Не входят новый APM-вендор, автоматическое
исправление, автоматическая блокировка по жалобам, browser control plane, изменение
CLI и локального реестра.

Поля политик и wire formats принадлежат их каноническим владельцам: данные —
`SPEC-013`, HTTP/API — `docs/contracts/` и `packages/contracts`, telemetry —
`SPEC-017`, moderation — `SPEC-016`, deployment и recovery — `SPEC-024` и
`docs/operations/runbooks/`. Эта спецификация не дублирует их schema или state
vocabulary.

## Термины

- `Readiness evidence` — безопасный, воспроизводимый набор результатов проверок
  для одного exact commit, configuration/policy revisions и окружения.
- `Operational policy` — утверждённая versioned policy для SLO, alerts, retention
  или abuse limits; численные значения не являются неявными defaults приложения.
- `Recovery rehearsal` — восстановление backup на изолированной копии данных с
  проверяемым результатом, не являющееся production restore.
- `Owner approval` — отдельное явное решение владельца допустить production change
  после проверки ещё действующего readiness evidence.

## Требования

- `REQ-3201`: Production change допускается только после успешной валидации
  production configuration; отсутствующий обязательный secret, policy reference,
  безопасная release identity или недоступная обязательная dependency дают
  наблюдаемый отказ до переключения трафика.
- `REQ-3202`: Доказательство готовности привязано к exact commit, environment и
  schema revision, а также к версионируемым operational policies; оно фиксирует
  outcome, timestamp, безопасные IDs/digests и именованные остаточные риски без
  секретов, tokens, значений env, private bytes или необязательных персональных данных.
- `REQ-3203`: Изменение commit, configuration/policy revision, schema revision либо
  истечение допустимого срока evidence делает прежний набор непригодным для owner
  approval и требует его пересбора.
- `REQ-3204`: SLO и alert policy утверждаются до production launch, имеют версию и
  связь с runnable operator response; telemetry покрывает как минимум API,
  authentication, dependency/readiness, queue, object storage, publication,
  moderation и rate-limit/abuse signals по `docs/operations/observability.md`.
- `REQ-3205`: Отсутствие или недоступность telemetry exporter не ломает приложение,
  но отсутствие обязательного readiness signal, policy или recorded alert-response
  не даёт собрать успешное production evidence.
- `REQ-3206`: Управление production-данными исполняет `SPEC-013`: экспорт,
  логическое и физическое удаление, хранение audit и backup имеют утверждённую
  policy, явного authorizer, безопасную диагностику и проверяемый outcome; прямой
  доступ к object storage не становится обходом authorization.
- `REQ-3207`: Ограничения частоты и защита от злоупотреблений применяются на server
  boundary до resource-intensive или sensitive mutation, различают безопасные классы
  клиента и не доверяют browser state, request headers или числу жалоб как полномочию.
- `REQ-3208`: Abuse signal, rate-limit rejection, staff read и staff lifecycle
  action сохраняют безопасную correlation/audit evidence. Ни один automated signal
  не блокирует, не скрывает, не удаляет и не раскрывает объект без существующего
  explicit audited staff decision.
- `REQ-3209`: Репетиция восстановления возвращает метаданные PostgreSQL и данные
  RustFS в изолированном окружении, проверяет готовность и согласованность
  метаданных с object storage, не выводит секреты или байты объекта в доказательство
  и не меняет production data.
- `REQ-3210`: Репетиция отката возвращает previous exact artifact под `deploy lock`,
  проверяет готовность и не выполняет destructive schema downgrade; при
  несовместимости сохраняет доказательство прерывания и следует `docs/engineering/schema-evolution.md`.
- `REQ-3211`: Owner approval возможен только для полного, действующего readiness
  evidence и является отдельным явным действием. Автоматизация, coding agent и
  зелёный CI не могут заменить approval или выполнить production mutation.
- `REQ-3212`: Инструкции оператора и доказательства выпуска связывают каждую
  обязательную проверку готовности с командой, ожидаемым результатом, инструкцией
  восстановления и владельцем; неисполненная проверка и остаточный риск записываются
  явно, а не выдаются за успех.
- `REQ-3213`: Safety validation имеет bounded telemetry для queue wait/run/requeue,
  scan count/cache/latency buckets и каждого check result/duration; offline
  benchmark фиксирует commit, policy, corpus, profile и отсутствие network/CLI,
  а измеренные latency не выдаются за универсальный cross-machine SLO.
- `REQ-3214`: Каждый вид компонента и сетап имеют от 10 до 20 релевантных
  вредоносных filesystem-примеров и не менее двух чистых контрольных примеров.
  Один последовательный платформенный
  сценарий прогоняет их через серверные проверки безопасности без сети, выдаёт
  машиночитаемый отчёт и отказывает при пропущенной атаке или ложной находке.

## Состояния и ошибки

Readiness evidence может быть `collecting`, `complete`, `rejected` или `expired`.
`complete` означает только полноту и успешность входящих проверок, а не факт
production deployment; после изменения его привязок или истечения оно становится
`expired`. Ошибки конкретных API и операций сохраняют зарегистрированные
`AI_STP_*` codes своих контрактов. Ошибка evidence выдаёт безопасную причину
неполноты и recovery instruction, не раскрывая конфигурацию или данные.

## Безопасность и приватность

Все боевые записи требуют явного подтверждения владельца. Доказательства,
оповещения, журналы, трассы и аудит используют разрешённый список полей; не содержат
секреты, сеансовые данные, закрытые байты объекта, необработанную диагностику,
полные локальные пути и значения окружения. Резервная копия остаётся защищённым
активом данных и не публикуется как доказательство. Ограничения злоупотреблений не становятся скрытым
профилированием, способом дискриминации или автоматической модерацией; staff
полномочия и data access остаются минимальными и
аудируемыми.

## Совместимость и миграция

Readiness evidence и policy references добавляются аддитивно. Existing API clients
не должны требовать новых полей до согласованного rollout. Новая policy revision
не переписывает historical evidence; она делает его непригодным для следующего
approval, если меняет применимую проверку. Новые telemetry и abuse controls сначала
проверяются с recorded outcome; production rollout остаётся owner-approved.

## Критерии приёмки

| Требование | Исполнимый способ проверки |
| --- | --- |
| `REQ-3201` | Проверка конфигурации отвергает отсутствующие secret, policy reference, release identity и dependency до traffic switch. |
| `REQ-3202` | Фикстура доказательства содержит только разрешённые identifiers/outcomes и не проходит при secret, token, env value или private bytes. |
| `REQ-3203` | Изменение каждой привязки или истечение времени делает previous evidence непригодным для approval. |
| `REQ-3204` | Проверка policy доказывает versioned SLO/alert policy и runnable response для каждого обязательного signal class. |
| `REQ-3205` | Приложение стартует при unavailable exporter, но readiness-evidence check не проходит без required signal/policy/response. |
| `REQ-3206` | Интеграционная матрица покрывает export, tombstone, purge, audit/backup retention и отказ direct object-store access. |
| `REQ-3207` | API tests доказывают server-side limits для anonymous/authenticated/sensitive paths и отсутствие client-side bypass. |
| `REQ-3208` | Проверка audit/redaction фиксирует abuse и staff events; N abuse signals не меняют lifecycle без staff action. |
| `REQ-3209` | Изолированная репетиция восстанавливает PostgreSQL и RustFS, проходит readiness/integrity check и не изменяет production fixture. |
| `REQ-3210` | Репетиция проверяет deploy lock, exact artifact rollback, readiness и отсутствие destructive downgrade. |
| `REQ-3211` | Негативная проверка доказывает, что CI/agent/automation без explicit approval не вызывает production mutation. |
| `REQ-3212` | Release-evidence inventory связывает обязательные checks с command, outcome, owner и recovery instruction. |
| `REQ-3213` | Unit-тесты проверяют bounded metrics snapshot, а `just safety-benchmark --iterations 3 --concurrency 1` выдаёт deterministic offline evidence с `network=disabled`, case order и scan/check/queue metrics. |
| `REQ-3214` | `just safety-corpus` читает versioned manifest, последовательно проверяет каждый файловый fixture и setup pin scenario, фиксирует per-kind counts, recall, false-positive rate и список несовпадений; scenario test требует полного обнаружения manifest expectations без clean findings. |
