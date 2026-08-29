---
description: "Capability-negotiated provider protocol v3 with one planned operation path."
last_verified: "2026-08-09"
---

# ADR-0061: Capability-negotiated provider protocol v3

Статус: принято; machine model и contract tests реализуются этим решением,
public provider releases и cross-repository E2E остаются обязательными условиями
ввода в эксплуатацию.
Дополнено `ADR-0085`: личность комплекта провайдера — его агрегатный digest.

## Контекст

Замороженные protocol v1 и v2 требуют один универсальный набор из двенадцати
команд. Эта форма противоречит нативным границам пяти провайдеров: Claude Code не
владеет программой и запуском, Codex и Pi намеренно не удаляют программу, а
`software-plan` не является общей реализованной возможностью. Формальное
соответствие вынуждало бы провайдер объявлять фиктивные действия или присваивать
себе чужое состояние.

Кроме того, v1/v2 разделяют изменение сетапа, восстановление и software lifecycle
на разные wire-команды. Для подготовленного и составленного сетапа нужен один
проверяемый путь: immutable `SetupDefinition` → `HarnessBundle` → чистый plan →
подтверждение exact digest → apply под блокировкой. Резервная копия, восстановление,
замена и удаление должны иметь ту же привязку плана, а permission profile не должен
становиться идентичностью сетапа.

## Варианты

1. Расширить v2 необязательными полями. Отвергнуто: v2 объявлен замороженным, а
   старый consumer не знает новых семантических ограничений.
2. Сохранить двенадцать команд и разрешить им возвращать `unsupported`. Отвергнуто:
   это оставляет универсальную поверхность нормативной и позволяет узнать об
   отсутствии возможности только после выбора неверной операции.
3. Ввести v3 с малым обязательным command core и capability-negotiated operations.
   Выбрано: provider сообщает правдивую закрытую модель до plan, а все изменения
   проходят через один plan/apply protocol.

## Решение

Protocol v1 и v2 остаются без изменений. Protocol v3 делит поверхность на
обязательную setup/bundle boundary и объявляемые возможности.

Состав команд и operations принадлежит `provider-kit/v3/manifest.json` и
перечислен там, а не здесь: запись решения фиксирует, почему граница проведена
именно так, а не что находится внутри неё на сегодня. Перечень в ADR устаревал бы
молча, потому что его никто не порождает.

Обязательная часть — команды setup/bundle core и operations материализации,
замены, копии, восстановления и удаления. Optional command вызывается только при
объявленной возможности; возможности жизненного цикла provider-owned программы и
запуска runtime перечисляются в `provider-info`, и consumer не вызывает
необъявленную операцию. Отказ имеет стабильный reason code и происходит до plan и
изменения цели.

`plan-operation` чистый и возвращает canonical provider plan artifact. План
связывает protocol/provider release, operation, canonical target и snapshot digest,
optional exact HarnessBundle, optional `BackupRef`, отдельный permission profile,
platform/runtime identity, expiry и ожидаемые эффекты. `apply-operation` принимает
сам план и его exact digest, получает canonical target lock и повторно проверяет
все preconditions после блокировки. Timeout или malformed response после возможного
эффекта означает `partial`, а не разрешение на blind retry.

Перед mutation provider публикует durable target-local journal `prepared`,
связанный с exact plan и target-bound `BackupRef`; после проверки результата он
публикует `committed`. Любой незавершённый journal/transaction/backup staging
блокирует чистый plan. `recover-operation` — отдельная подтверждённая mutation
граница: фаза `prepared` восстанавливается из точной копии, а `committed` лишь
проверяет результат и завершает cleanup. Consumer `resume` сначала читает status,
может дренировать этот журнал, но не повторяет apply вслепую.

Prepared и composed setup различаются только происхождением finalized immutable
`SetupDefinition`. После finalization они используют одинаковые HarnessBundle,
пути проверки, плана, подтверждения, применения, состояния, копии, восстановления и удаления.

`provider-info` содержит хэш build manifest и адресуемый содержимым профиль проекции: поддержанные компоненты
kinds, projection kinds, native identifier namespaces, collision/ownership rules,
bundle formats, limits, OS/architecture и digest профиля. Compiler строит native
operations только по exact профилю, а provider независимо повторяет проверку.
Неизвестный компонент, поверхность, операция, протокол или digest профиля закрывается
отказом; silent drop и best-effort conversion запрещены.
Conversion report также связывает projection kind, а каждый component обязан
владеть непустым exact native content. Provider-owned validators проверяют
синтаксис нативных JSON/TOML и обязательные маркеры деревьев до plan.

Provider state и BackupRef сохраняют как минимум protocol/provider build и release,
harness/target identity, SetupVersion passport digest, ordered exact component refs
и хэши содержимого, хэш SetupDefinition, логический bundle и хэш raw artifact,
хэш provider plan, идентичность операции, предусловие цели и native ownership
manifest, предыдущую verified identity и состояние drift. Секретные значения не
сохраняются. Read-only `status` никогда не мигрирует старый stamp: migration
происходит только в подтверждённой mutation после резервной копии.

Network policy остаётся честной моделью ADR-0047. Local validation/plan/status и
локальные apply phases требуют доказанного `none` enforcement. Software download
имеет отдельную `artifact_download` phase, последующий apply снова локален. Launch
объявляет `runtime_external`.

## Последствия

Public provider может соответствовать общему protocol, не присваивая себе
host-owned software. Claude Code корректно объявляет отсутствие software/launch;
Codex и Pi — отсутствие software removal. Grok Build и OpenCode могут объявить
полный software lifecycle только при реальной реализации.

Появляется новый неизменяемый публичный артефакт соответствия: схемы и эталонные примеры,
hostile corpus и expected digests. Public providers не зависят во время исполнения
от закрытого контура авторинга или private `ai_stp`; они проверяются против exact
точной опубликованной версии набора, а закрытый control plane повторяет E2E и проверки promotion.

Миграция выполняется provider-first. Старые standalone stamps читаются без
изменения, затем первая подтверждённая v3 mutation создаёт backup и атомарно пишет
новую схему происхождения. Версия protocol и release digest выбираются по проверенному
provider release manifest до запуска и не повышаются ответом неизвестного процесса.
Provider не заявляет digest архива, внутрь которого сам входит: consumer связывает
его отдельно с независимым build digest.

## Условия пересмотра

Решение пересматривается, если все поддерживаемые продукты получают одинаковое
нативное ownership software/launch либо provider process заменяется единым trusted
runtime с эквивалентной capability и isolation model.
