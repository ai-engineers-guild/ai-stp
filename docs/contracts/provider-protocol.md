---
description: "Команды, граница исполнения и соответствие состояний публичного провайдера."
last_verified: "2026-08-28"
---

# Протокол провайдера

Владелец требований — `SPEC-008`. Здесь зафиксирована машинная граница: набор команд, правила запуска и соответствие состояний.

## Замороженные обязательные команды v1/v2

```text
provider-info
software-status
software-plan
software-install
software-update
software-remove
validate-bundle
plan-bundle
apply-bundle
status
restore
launch
```

`provider-info` сообщает версию протокола, идентификатор харнесса, версию провайдера, поддерживаемые действия, форматы пакета, системы, архитектуры и ограничения. Закрытая проверка сравнивает этот ответ с реально доступными действиями CLI.

## Граница исполнения

Команда получает массив аргументов, использует `shell=false`, явный абсолютный целевой каталог, точный исполнимый файл, отфильтрованное окружение, ограничение времени и объёма вывода.

Точный provider artifact проверяется до запуска: путь должен разрешаться в обычный
файл с execute permission на текущем host. Существующий, но неисполняемый файл
возвращает `AI_STP_DEPENDENCY_UNAVAILABLE`, а не внутреннюю ошибку процесса.

Ограничение объёма вывода ограничивает то, что **читают**, а не то, что сохраняют. Вызывающая сторона читает не более предела и останавливает провайдера, вышедшего за него; ответ такого провайдера не разбирается, а называется отказом. Предел, применённый после чтения до конца, не ограничивает ничего: он оставляет память вызывающей стороны в распоряжении чужой программы.

Отфильтрованное окружение — список разрешённых имён с настоящими значениями, а не те же имена, обнулённые. Провайдер без `PATH` не может стартовать вовсе, и такой сбой читается как поломка провайдера, а не вызывающей стороны.

Команды чтения не создают состояние. `validate-bundle` и `plan-bundle` не изменяют цель. `apply-bundle` принимает точный хэш плана, получает блокировку и повторно проверяет цель после блокировки.

## Точная передача HarnessBundle

Три bundle-команды получают одну и ту же неизменяемую привязку после общих
аргументов протокола `--target` и, для v2, `--phase`:

```text
--bundle <absolute-content-addressed-path>
--bundle-format ai-stp-bundle/1
--bundle-digest sha256:<logical>
--artifact-digest sha256:<raw-zip-bytes>
--bundle-size <decimal-bytes>
```

`plan-bundle` добавляет `--expected-target-digest <digest>`. `apply-bundle`
получает тот же аргумент и `--plan-digest <provider-plan-digest>`. Порядок выше
является частью argv contract; путь указывает на обычный файл, не на каталог или
ссылку. Путь не входит в идентичность и не сохраняется в плане: идентичность
задают формат, два digest и размер.

Provider response повторяет `bundle_format`, `bundle_digest`, `artifact_digest`
и числовой `bundle_size`. `validate-bundle` дополнительно возвращает `valid=true`.
`plan-bundle` возвращает `state=planned`, canonical SHA-256 `plan_digest`, тот же
`expected_target_digest` и непустой список строк `effects`. `apply-bundle`
возвращает собственное состояние, тот же target digest и exact `plan_digest`.
Командно-специфичные дополнительные поля, например `backup_ref`, разрешены, но не
заменяют обязательные echoes.

### Что покрывает `target_digest`

Digest считается **над управляемыми путями, а не над каталогом**, в котором они
лежат: обходятся корни из `native_namespaces` провайдера, а его собственный
control-каталог и записи, которые он не считает своими, исключаются.

Это не косметическое уточнение. При чтении «над целью целиком» под `user_root`
любая запись соседнего продукта между планом и применением неотличима от дрейфа,
и операция отказывает — на корне, в который четыре продукта пишут по замыслу.
Отказ тем чаще, чем успешнее конвенция. При чтении «над управляемыми путями»
`skills` чужого продукта в digest не входит, и области значат одно и то же.

Объявленный набор перед обходом сокращается до **покрытия**: пространство имён,
вложенное в другое объявленное, посещается один раз. Иначе identity зависела бы
от того, как сформулирована декларация, — а во время переходного окна родитель и
потомок объявлены оба (`plugins` и `plugins/local` у cursor,
`antigravity-cli/plugins` и `config/plugins` у antigravity), и байты потомка
нельзя хешировать дважды.

Записано после того, как выяснилось, что слово встречалось только в утверждениях
о том, что digest *доказывает*, и ни разу — в предложении о том, что он
*покрывает*. Реализация оказалась верной; совпадение не является контрактом.

После собственной блокировки цели provider возвращает `stale`, если её digest
уже отличается от `expected_target_digest`, и не выполняет эффект. Consumer
сохраняет это как терминальный `stale`, а не как `partial`: точный ответ с
обязательными echoes доказывает отказ до эффекта. Ошибка ответа или несовпадение
echoes после вызова по-прежнему означает `partial`, потому что тогда отсутствие
эффекта не доказано.

Consumer проверяет echoes до записи результата. Несовпадение validation или plan
блокирует создание operation plan. Несовпадение после вызова apply означает
`partial`, потому что отсутствие проверяемого ответа не доказывает отсутствие
эффекта. Перед apply consumer заново проверяет raw SHA-256 и размер cached bytes;
потерянный или повреждённый artifact блокирует вызов. Observe-only `resume`
вызывает только `provider-info` и `status` и никогда не повторяет `apply-bundle`.

## Диагностика управляемых путей

План установки показывает относительные `managed_paths` точного сохранённого
HarnessBundle. При `local_drift` команда `target diff` сравнивает их с
`provider_target` последней verified operation и возвращает `managed_detail`:
`available`, `unavailable` либо `not_applicable`. Доступная детализация содержит
`managed_changes` со стабильными кодами `modified`, `added`, `deleted`,
относительным путём и SHA-256 evidence; небезопасная ссылка обозначается
`observed_digest=unsafe`.

Осмотр ограничен managed roots, не следует по символическим ссылкам, не показывает
абсолютный локальный путь и не изменяет цель. Потеря точного bundle, target binding
или verified history не угадывается по текущему каталогу, а закрыто возвращает
`unavailable`. Результат является доказательством для пользователя и плана;
восстановление или очистка им автоматически не запускаются.

## Сеть и версия границы

Замороженный protocol v1 не объявляет сетевую потребность и не устанавливает
сетевую изоляцию процесса. Отсутствие сетевых полей в `Boundary` и успешное
выполнение команды не являются доказательством запрета сети. Поэтому v1 нельзя
использовать как подтверждение сетевого класса вредоносного корпуса `#184`.

Сетевая способность вводится только protocol v2 по
`ADR-0047-provider-network-capability.md`. Каждое действие объявляет
`network_requirement` со значением `none`, `artifact_download` или
`runtime_external`, а результат сообщает `network_enforcement`: `enforced`,
`unavailable` или `not_requested`. При требовании `none` отсутствие доказанного
механизма изоляции означает типизированный отказ до запуска. Неизвестная версия
протокола не разбирается оптимистично, а v1 не расширяется дополнительными полями.

Закрытая матрица command/phase, wire schema и pre-invocation решение v2 находятся в
`ai_stp_cli.provider.protocol_v2`. `software-install` и `software-update` имеют
отдельные `download` и `apply`: первая фаза объявляет `artifact_download`, вторая —
`none`. Одна модель не выдаётся за сетевую песочницу: без доказанного launcher на
текущей ОС она возвращает `unavailable` и не закрывает `#184`.

Каждый v2-вызов передаёт обязательные аргументы `--phase <phase>` и
`--target <absolute-directory>`. Отсутствующая или неизвестная фаза не угадывается.
Версию до первого `provider-info` выбирает проверенный release manifest или явный
conformance-вызов consumer, поэтому ответ непроверенного процесса не может сам
переключить границу с v1 на v2. Наблюдённый `network_enforcement` добавляет consumer
рядом с provider payload; значение из самого payload не является доказательством.
Команда `provider conformance --protocol-version 2` проверяет точное объявление v2,
закрытую матрицу каждой пары команды и фазы, решение consumer, общий вредоносный
корпус, состояния и повторяемость чтения. Без аргумента она сохраняет замороженное
поведение v1.

Conformance передаёт не JSON-заглушки, а временные literal ZIP-артефакты по тому же
exact argv contract, что и установка. Валидный пакет обязан пройти validation и
side-effect-free plan с точными echoes. Каждый hostile case получает отдельные
content-addressed bytes: пути, повтор, link/special metadata, предел, неизвестную
поверхность, несовпадающий digest или неподдерживаемую версию. После прогона corpus
удаляется. Conformance не вызывает `software-install/update/remove`, `apply-bundle`,
`restore` или `launch` на переданной пользователем цели: доказательство этих действий
принадлежит provider E2E с одноразовой целью и подтверждённым планом.

Для Linux реализован отдельный Bubblewrap launcher. Capability становится `enforced`
только после положительного контроля доступности локальных IPv4, IPv6 и DNS-UDP
endpoints снаружи и наблюдаемого запрета тех же transports внутри нового network
namespace. Проверяется точный путь, версия и SHA-256 `bwrap`; group/world-writable
либо не-root-owned executable/ancestor отвергается. Команда `provider network --json` применяет closed v2 decision
и сообщает capability; при `unavailable` локальные v2 actions недоступны. Launcher
оборачивает точный provider argv через `ai_stp_cli.provider.invocation_v2`; разрешённая
download-фаза проходит без сетевого namespace, а apply снова требует доказанный
launcher. `install plan` выбирает версию до первого вызова, сохраняет её и абсолютный
provider target в неизменяемом плане, а `apply` и `resume` используют только эту
одобренную версию. Поэтому v2 lifecycle проходит через тот же phase invoker и не
может быть понижен аргументом после подтверждения. Реальные provider releases
остаются отдельным release evidence. Текущая цель — six-leg matrix по
`ADR-0113`; старый Linux-only профиль заменён.

**Protocol v3 на трёх ОС.** Linux использует Bubblewrap. Windows использует
native AppContainer launcher, который запрещает сеть дочернему process tree и
доказывает доступ к выбранному target runtime probes; невозможность построить
его даёт ранний fail-closed. macOS пока не имеет network-denying launcher.

На macOS unisolated local phase разрешается ровно двумя наблюдаемыми причинами:
доверенный выпуск либо явный `--unverified-provider`. Исключение не становится
`enforced` и не переносится на неизвестный executable. `provider network
--json` сообщает отдельный `v3_local_phase`:

- `network_denied` — launcher доказан, фаза идёт внутри него;
- `unisolated_by_trust` — launcher'а на этой платформе нет, фаза идёт с
  достижимой сетью, и `v3_local_phase_reasons` перечисляет причины, одну из
  которых обязан предъявить вызывающий;
- `refused` — launcher здесь возможен и отсутствует, поэтому не идёт ничего.

Последние два не сливаются намеренно: отсутствие установленного launcher на
Linux/Windows — недостающая зависимость или runtime capability; отсутствие
механизма на macOS — известная граница платформы. Проверка импортов provider
binary является дополнительным evidence и не заменяет изоляцию process tree.

## Capability-negotiated protocol v3

Protocol v3, принятый `ADR-0061-capability-negotiated-provider-protocol-v3.md`, не
меняет v1/v2. Он отделяет обязательную wire boundary от нативных product
capabilities и имеет закрытый набор команд и operations.

Состав этих наборов принадлежит одному владельцу — `provider-kit/v3/manifest.json`,
порождаемому из `apps/cli/src/ai_stp_cli/provider/protocol_v3.py`. Точную ревизию
называет `provider-kit/v3/KIT-IDENTITY.json` (`ADR-0085`). Здесь перечня нет
намеренно: словарь, записанный прозой во втором месте, расходится с исполняемым
источником, и обнаруживается это уже после того, как кто-то реализовал прозу.

`provider-kit/v3/provider-info.schema.json` объявляет
`$id: https://nddev.asia/schemas/provider-protocol/v3/provider-info.json`. По
JSON Schema 2020-12 это **идентификатор**, задающий базовый URI. Те же байты,
что в комплекте, отдаются по этому адресу: внешний валидатор, который за ним
пойдёт, получает схему, а не 404. Реализации по-прежнему сверяют комплект
локально по `SHA256SUMS`; сетевой ответ не заменяет `KIT-IDENTITY.json`.

`provider-kit/v3/status-response.schema.json` объявляет закрытую форму ответа
`status`. Всегда обязательны protocol/provider/harness identity, canonical
target, `state`, оба target digests, `cleanup_state`, `journal`, `backups`,
`provider_state` и `shadowed_by`. Когда вложенный `provider_state` одновременно
`present=true`, `readable=true` и `drift_state=clean`, схема дополнительно
требует полный flat provenance: state/provider/release/setup/bundle/plan,
operation/precondition, native ownership, written paths, backup и previous
verified identity. Для missing, foreign-schema и local-drift ответ не обязан
придумывать clean provenance.

Схема, checksum и conformance cases публикуются раньше enforcement. До выпуска
provider systems, которые вендорят эту ревизию kit, consumer продолжает читать
совместимый status прежних релизов; наличие schema в kit само по себе не означает,
что runtime уже отклоняет старый ответ.

Ниже — только то, чего машинный файл не выражает: смысл делений.

Команды делятся на общий setup/bundle core и optional. `launch` является optional
command и допустим только при объявленной capability; его отсутствие в parser для
provider без launch ownership является корректным соответствием.

Operations делятся так же. Core покрывают материализацию, замену, копию,
восстановление и удаление provider-owned setup projection; optional покрывают
жизненный цикл provider-owned программы и запуск runtime через нативную границу.

Все семь текущих systems объявляют software install/update/remove, но availability
проверяется по platform artifact. Complete launch объявляют пять; Cursor и
Antigravity launch не объявляют. Consumer не вызывает необъявленную operation.
Unknown operation/component/native surface,
формат, protocol, projection profile, OS или architecture отклоняются со стабильным
reason code до plan и изменения цели. Профиль разрешений, которого нет в закрытом
`permission_profiles`, это не `unsupported_operation` и не
`projection_profile_mismatch`.

`provider-info` возвращает digest build manifest и content-addressed
projection profile: component/projection kinds, native identifier namespaces,
bundle formats, limits, permission profiles, OS и architectures. Compiler строит
projection только для exact профиля, а provider независимо проверяет bundle.
Permission profile является отдельным plan input и не входит в setup/component digest.

Набор полей `provider-info` закрыт и сравнивается на точное равенство, поэтому
неизвестное поле отклоняет весь ответ, а не его часть. Единственное необязательное
имя — `scoped_projection_profiles`: массив профилей, каждый из которых объявляет
`target_scope` из словаря `global` / `project`. Запись со значением `global`
отклоняется, потому что глобальную область объявляет `projection_profile`; области
в массиве уникальны; digest каждой записи связывает её декларацию вместе с
областью. Отсутствие массива означает владение только глобальной областью и не
является деградацией. `projection_profile` не меняется ни одним полем, поэтому
declaration и digest релиза, выпущенного до этого расширения, остаются прежними.
Разрешение области выполняется один раз, к моменту планирования, когда цель уже
известна; plan artifact и status по-прежнему несут один `projection_profile_digest`
— digest разрешённого профиля. Решение и порядок выпуска — `ADR-0125`.

Необязательный жизненный цикл программы (`software_install`, `software_update`,
`software_remove`) не добавляет команд: те же `plan-operation` и
`apply-operation`, те же журнал, backup и plan-digest. Провайдер не открывает
сокет. `plan` отвечает точной идентичностью артефакта офлайн; кто держит сеть,
забирает эти байты; `apply` сверяет digest и длину с планом и распаковывает
офлайн. Провайдер, который не объявил эти operations, их не планирует.

`--target` — каталог конфигурации. `--prefix` — каталог программы. Это разные
пути с разным временем жизни, оба абсолютные. `--software-version` опущен —
закреплённая версия; передан — ровно эта версия, иначе отказ. Незакреплённая
платформа отказывается кодом `unsupported_platform`.

План несёт массив `software_artifacts`. Один элемент — один файл; несколько —
несколько, в том же порядке, в каком `apply` получит повторённый флаг
`--software-artifact`. Поля элемента: `platform`, `url`, `sha256`,
`byte_length`, `entry_point`. Каталог на apply не скрывает, какой файл какой
записи плана соответствует. `software_remove` — plan и apply без download и
без `--software-artifact`.

`apply-operation` остаётся в `forbidden_in_safe_conformance`. Чистота `plan`
для объявленного жизненного цикла программы проверяется: провайдер, который объявил
операцию и не умеет назвать артефакт офлайн, как раз тот отказ, который этот
контракт должен ловить.

`plan-operation` всегда чистый. Он связывает стабильный operation ID, operation, canonical target и snapshot,
сборку provider, проверенный consumer хэш выпуска и protocol, точные идентичности optional bundle и optional `BackupRef`,
permission profile, platform/runtime identity, expiry и effects. `apply-operation`
получает канонический plan artifact и точный digest, берёт блокировку цели, а после
lock повторно проверяет preconditions. Ответ успеха несёт `state`, тот же
`plan_digest` и `expected_target_digest`; четыре bundle-echo остаются на
`validate-bundle` и `plan-operation`. Типизированный отказ после lock — это
`state=refused` с `reason=stale` (нет эффекта) либо `state=stale`. Несовпадающий
или истёкший plan не имеет эффекта. Timeout/malformed response после возможного
эффекта даёт `partial` без автоматического повтора. `status` после install
доказывает `state=managed`, `target_digest`, protocol/provider identity и drift
`clean` или `verified`; вложенный `provider_state` допустим.

Provider перед первой записью публикует target-local durable journal в фазе
`prepared`, связанный с exact plan digest, operation ID и target-bound `BackupRef`.
После проверки результата journal атомарно переходит в `committed`; его очистка
происходит только после durable state. Наличие journal, transaction directory или
неполного backup slot делает `plan-operation` чистым отказом `recovery_required`.
Единственная команда, имеющая право разобрать это состояние, —
`recover-operation`: `prepared` восстанавливает точный pre-operation target,
`committed` только проверяет exact result и очищает хвосты. `resume` может вызвать
эту команду после read-only `status`, но никогда не повторяет `apply-operation`.

Подготовленный exact graph и composed graph после finalization образуют один неизменяемый сетап,
`SetupDefinition` и проходят одинаковые HarnessBundle, plan, confirmation, apply,
общие пути состояния, копии, восстановления и удаления. Channel/marketplace являются acquisition или
projection metadata, а не setup identity.

Provider state связывает protocol/release/harness/target, SetupVersion passport и
SetupDefinition, ordered exact components, logical bundle/raw artifact,
projection-profile/provider-plan, operation/precondition, native ownership,
`BackupRef`, предыдущую verified identity и состояние drift. Секретные значения запрещены.
`status` не мигрирует старый stamp; mutation сначала создаёт backup, затем атомарно
пишет новую schema.

Запись преобразования связывает вид компонента, нативную поверхность и вид проекции.
Каждый exact component обязан владеть хотя бы одним manifest-bound native file.
Provider повторно проверяет продуктовую грамматику (например JSON/TOML) и
обязательные маркеры полного дерева (`SKILL.md`, `plugin.json`, `package.json`)
до plan; silent truncation каталога и пустая projection запрещены.

Release digest не берётся из `provider-info`: это создало бы самоссылку артефакта.
Consumer проверяет exact executable/release до запуска, передаёт его digest в plan и
сверяет с неизменяемой операцией; provider сообщает независимый хэш build manifest.

Машинная declaration и closed wire schema принадлежат
`ai_stp_cli.provider.protocol_v3`. Public conformance kit распространяется отдельно
от закрытого control plane и содержит точные схемы, examples, hostile corpus и
expected digests; зависимость public provider во время исполнения от private repository запрещена.

## Наблюдение внешней авторизации

Exact выбранный `SetupVersionPassport` объявляет требование
`requires_authorization`. Только provider владеет нативной целью и может наблюдать,
завершена ли соответствующая настройка. Поэтому ответ `status` может содержать
необязательное command-specific evidence:

```json
{
  "authorization": {
    "kind": "external_service",
    "state": "pending"
  }
}
```

Закрытые `kind` — `user_account` и `external_service`, закрытые `state` —
`pending` и `ready`. Поле не содержит идентификатор пользователя, адрес входа,
токен или иной секрет. Отсутствие поля сохраняет совместимость protocol v1, но не
доказывает готовность: объявленное паспортом требование остаётся
`needs_configuration`. Только совпадающий `kind` со `state=ready` снимает ожидание;
неизвестная форма и несовпадение закрываются типизированным отказом. Полный rationale
зафиксирован в `ADR-0052-provider-observed-authorization-readiness.md`.

`install plan` показывает объявленный `required_authorization` до изменения цели.
Успешный apply не подменяет readiness: агент после настройки вызывает `target status`
с тем же точным provider и объясняет оставшееся требование из machine output, а не
угадывает его по локальному флагу или наличию секрета.

## Соответствие состояний

Провайдер и `ai_stp` ведут собственные журналы. Результат провайдера отображается в долговечную операцию по `contracts/operation.md` однозначно:

| Состояние провайдера | Состояние операции `ai_stp` |
|---|---|
| `planned` | `planned` |
| `applying` | `applying` |
| `applied_unverified` | `applied_unverified` |
| `verified` | `verified` |
| `partial` | `partial` |
| `failed` | `failed` |
| `stale` | `stale` |
| `rolled_back` | `rolled_back` |

Состояния `approved` и `cancelled` принадлежат только операции `ai_stp` и не имеют источника у провайдера. Применённое, но не проверенное состояние не называется успехом.

## Пакет

Внешний пакет соответствует `harness-bundle.md`. Провайдер отклоняет неподдерживаемую версию, выход из каталога, ссылки, специальные устройства, конфликт путей, превышение пределов, неизвестную нативную поверхность и несовпадение хэша.

## Резервная копия и частичный сбой

Резервная копия создаётся до первого изменения; байты принадлежат провайдеру, `ai_stp` хранит точную ссылку. Новый сетап устанавливается в неактивную цель, указатель следующего запуска меняется после проверки состояния и готовности к запуску.

Истечение времени после возможного эффекта, сбой восстановления и неизвестное состояние возвращают `partial` с последним подтверждённым состоянием. Повтор без отдельной проверки восстановления запрещён.
