---
description: "Замещённый снимок пяти provider v3 эстейта NDDev-it-com; текущий эстейт — семь NDDev-OpenNetwork setup-systems."
last_verified: "2026-08-28"
---

# Готовность public providers

> **Замещён.** Этот снимок описывает эстейт `NDDev-it-com/*-app`, снятый
> `ADR-0119`/`ADR-0120`. Те пять репозиториев переведены на личный аккаунт
> `rldyourmnd` и заархивированы 2026-08-25 — проверено против API, а не по
> отчёту. Текущий эстейт — **семь** `NDDev-OpenNetwork/*-setup-system`, все на
> `0.0.16`, реализация на Rust, а не Python-адаптеры, описанные ниже.
>
> Сохранён как запись выполненной работы: merge SHA и номера PR остаются
> проверяемыми фактами о том, что было сделано. Не читать как текущее
> состояние — за ним `provider-policy.toml` и `just evidence-providers <tag>`.

## Назначение и граница

Это датированный снимок issues `#170`–`#172` и `#190`–`#192`, а не нормативный
контракт провайдера. Нормативные команды, модель возможностей и граница исполнения
принадлежат `provider-protocol.md`, `SPEC-008` и `ADR-0061`.

Provider repositories являются отдельными mutation boundaries. Этот снимок не
разрешает новый push, tag, GitHub Release или публикацию артефакта.

## Точный снимок реализации

| Provider repository | Merge SHA | PR | Provider v3 implementation |
| --- | --- | --- | --- |
| `NDDev-it-com/nddev-claude-app` | `dbdc6b3df0968d9b41b05724b74ccc8bfcf8439c` | `#11` | слита |
| `NDDev-it-com/nddev-codex-app` | `24c0688008c85398772bb97777da0c0116afc3d2` | `#41` | слита |
| `NDDev-it-com/nddev-grok-build-app` | `37526b9ba8783f098fdf86c4ad30b748bc74612a` | `#8` | слита |
| `NDDev-it-com/nddev-opencode-app` | `d3a85f5f4ccb93156fd28d0d9679dd23de7bce82` | `#7` | слита |
| `NDDev-it-com/nddev-pi-app` | `cdfca6c19d31222e237d18fa023b2d5ec13745f0` | `#10` | слита |

Все пять repository checkout содержат `provider_protocol_v3.py` и
`provider_runtime_v3.py`. Их adapters реализуют единый prepared/composed путь
через immutable SetupDefinition, exact HarnessBundle, provider plan, backup,
операции применения, состояния, восстановления, удаления и отката. Согласование возможностей не заставляет
provider заявлять software или launch operation, которой нативный manager не
владеет.

## Что доказано в ai_stp

- protocol v3 имеет отдельные schemas, hostile corpus и content-addressed public
  provider kit;
- потребитель связывает снимок цели, точные байты пакета, профиль проекции,
  provider plan, release digest и recovery journal;
- реальный межрепозиторный тест существует для всех пяти адаптеров и выполняет
  установку, замену, резервирование, удаление и откат на одноразовой цели;
- подготовленный и составной режимы получения дают один точный путь пакета;
- обычный CI сохраняет эти tests как explicit opt-in и не выдаёт skipped test за
  release evidence.

Ручной локальный прогон real adapters полезен как integration evidence, но не
заменяет immutable release artifact и exact release run.

## Linux integration evidence

На `2026-08-09` общий disposable-target test выполнен из exact tree
`ai_stp@4e546443a3043c1af8e9511892fca87b50f6e17a` на
`rldyourmnd-server-omen`, Linux x86_64, kernel `7.0.0-29-generic`, Python
`3.13.14`. Все пять provider checkout были чистыми и совпадали с merge SHA из
таблицы выше.

Тест `test_real_v3_full_setup_lifecycle_uses_one_exact_bundle_path` получил пути
пяти исполняемых manager entrypoints через отдельные переменные окружения и для
каждого provider прошёл install, update через подготовленную ссылку, backup,
remove и rollback на временной цели. Наблюдаемый результат: `5 passed` за
`71.82s`, без пропусков. Точный digest пакета и literal artifact digest совпали
между composed и prepared acquisition.

Этот исходный прогон доказал совместимость merge SHA с consumer до публикации.
Следующий раздел фиксирует отдельное release evidence и не подменяет его этим
историческим запуском.

## Exact releases

На `2026-08-10` из чистых release-коммитов собраны, подписаны offline Ed25519
ключом `ed25519:b1d0fb8743bd1c0bacbb3c61` и опубликованы immutable GitHub Releases.
Каждый release содержит executable и подписанный manifest с `sequence = 1`,
`protocol_version = 3`, `supported_os = ["linux"]` и
`supported_arch = ["x86_64"]`.

| Provider | Release commit | Tag | Executable SHA-256 |
| --- | --- | --- | --- |
| Claude Code | `4082a42f4d92653ed379721b4cd08906e5059dd5` | `0.2.0` | `57f9da3c8d821c8443fdff1d119dffb788ef78e73c35317e30c3914662c494f0` |
| Codex | `138e876616ee16bea155d00a1589f4639c45addf` | `0.2.0` | `79ca9431db7e3d602f8fd70d1c03bc52c6bf2d14c5d7f7048f10a34231305adc` |
| Grok Build | `307e5124a1919a2224692cc8d64c50f98364ef2b` | `0.3.0` | `3da44c75c42efa1dbc6de1900fb6820af3d6ada903847df7e0dfa8f5c6e9a3aa` |
| OpenCode | `ecb1380f56124867520700f0ccf9b05801293863` | `0.3.0` | `97bcd9c18fe580d7c2fb5d0ca3b9a960bb5a7834ad1c12d1a7d4b2b2c361d498` |
| Pi | `2fbb9d0dff2f28076868e4f0457d7ed48aa5263f` | `0.2.0` | `beb1ede511b3568591382a732d5668cd3f451b1fbad6005353dc9cc32694b2d3` |

GitHub API повторно подтвердил, что пять tags указывают на эти commits, releases
не являются draft/prerelease, имеют `immutable = true`, содержат ровно два asset,
а серверные asset digests совпадают с локальными байтами.

Подписанный harness evidence прошёл полный lifecycle каждого provider: Claude Code
— 9 шагов, Codex — 13, Grok Build — 14, OpenCode — 14 и Pi — 13. Затем consumer
`ai_stp` выполнил один параметризованный тест точного артефакта для всех пяти
выпусков: `install`, `verify`, `status`, `update`, `remove` и `rollback`; результат —
`5 passed`, без пропусков. Manifest участвовал в plan digest, release trust был
положительным, а локальный anti-rollback floor стал `1` только после verified apply.

## Оставшийся gap

Для каждого provider уже закрыты:

1. точный исполнимый артефакт из чистого merge SHA;
2. манифест сборки, исходный digest, подпись Ed25519 и монотонная последовательность выпуска;
3. public provider-kit v3 conformance;
4. закрытый hostile/effect corpus;
5. disposable-target install, replace, backup, remove и rollback на текущей
   доказанной release platform;
6. точное закрепление дайджеста артефакта и открытого ключа автономной подписи в
   закрытой политике `ai_stp`;
7. anti-rollback evidence через настоящий artifact, а не fixture.

Отдельно остаются key-rotation/recovery drill будущего выпуска и повтор evidence на
финальном CLI release-candidate SHA. Они не отменяют текущую доказанность первых
immutable provider releases.

По `ADR-0062` текущий обязательный release profile — Linux x86_64. macOS остаётся
отдельной будущей portability line и получает `not_verified`, пока нет её run.

## Повтор на CLI-кандидате 2026-08-13

На `ai_stp@93fc61cf57a452d5b42a29bf4a5aa5b3134df6a3`, Linux
`7.0.0-29-generic` x86_64, повторно загружены публичные неизменяемые assets и
подписанные manifests Claude Code `0.2.0`, Codex `0.2.0` и Grok Build `0.3.0`.
Хэши исполняемых файлов совпали с закреплённой политикой:

- Claude Code — `57f9da3c8d821c8443fdff1d119dffb788ef78e73c35317e30c3914662c494f0`;
- Codex — `79ca9431db7e3d602f8fd70d1c03bc52c6bf2d14c5d7f7048f10a34231305adc`;
- Grok Build — `3da44c75c42efa1dbc6de1900fb6820af3d6ada903847df7e0dfa8f5c6e9a3aa`.

Параметризованный тест настоящих провайдеров прошёл три строки без пропусков. Каждая
строка выполнила `plan` и `apply` из полного HarnessBundle, повторное чтение `status`
в новом вызове, контролируемое изменение нативной управляемой инструкции,
неизменяющее обнаружение `local_drift` и точный `diff`, явно подтверждённый
`update`, повторный `status` без расхождения, `backup`, `remove` и `rollback`.
Подготовленный сетап и исходное предложение дали одинаковые логический и
буквальный хэши HarnessBundle; нижняя граница выпуска продвинулась только после
проверенного применения. Наблюдаемый результат —
`3 passed`; длительности строк: Claude Code `15.08s`, Codex `18.63s`, Grok Build
`19.07s`.

Протокол v3 намеренно не обещает `launch`: Claude Code не владеет запуском
харнесса, а общая модель возможностей не допускает фиктивной обязательной команды.
Поэтому «следующий запуск» в общем доказательстве означает новый процесс CLI,
который читает provider status и подтверждает точную установленную поверхность.
Специфичный для Grok Build запуск остаётся проверкой его публичного модуля и не
переносится в общее ядро протокола.

## Порядок выполнения

1. Влить exact pins и trust anchor в `rldyourmnd` после exact-head CI.
2. Записать release evidence в `#170`, `#171`, `#190`, `#191`, `#192`.
3. Закрыть `#172` после слияния политики потребителя и повтора корпуса доверия.
4. Закрывать `#175` и `#176` только после repeat run на финальном CLI
   release-candidate SHA.
5. Перед расширением support matrix отдельно выпустить macOS artifacts и получить
   `not_verified` -> `verified` evidence; текущий Linux release этим не блокируется.

## Доказательства закрытия

- repository/ref/SHA и clean status;
- artifact digest, signature, signer и sequence;
- public/closed conformance report;
- target-before, plan digest, backup reference, target-after и rollback result;
- Linux distribution/architecture/runtime versions;
- network requirement/enforcement result каждой выполненной phase;
- точные команды, exit codes, skipped/not-run причины и residual risks.
