---
description: "Server-owned read models для внешнего evidence и account-scoped selection impact без изменения доменного доверия."
last_verified: "2026-08-15"
---

# ADR-0094: Server-owned consumer read models

Статус: принято. Части GitHub archive read model и account blast-radius
delivery заменены `ADR-0096`. Canonical copy, deep-link и прочие consumer
решения этого ADR продолжают действовать.

## Контекст

`SPEC-030`, `SPEC-043` и `SPEC-044` уже имеют работающие shared/CLI-половины,
но web и server пока не проецируют их полностью:

- web дублирует шаблоны CLI copy и уже расходится с canonical parser;
- catalog не показывает GitHub archived observation;
- account/org-wide selection impact и blast radius отсутствуют в API/web;
- local CLI report нельзя выдавать за server-wide полноту;
- public catalog request не должен становиться прокси для GitHub API.

Существующие решения продолжают действовать: `ADR-0064` владеет pure
deep-link grammar, `ADR-0082` разделяет external GitHub fact и lifecycle, а
`SPEC-043` запрещает отправлять private content внешнему tokenizer. Нужно
зафиксировать только новую boundary: где живут server observations, кто строит
account projection и как web получает её без второй доменной модели.

## Решение

### 1. Server владеет только server read model

Server хранит bounded observation history для публичного GitHub metadata и
account-scoped projection для synced entities. Это не становится новым
источником истины паспорта, lifecycle или trust.

Последнее observation и append-only history разделены логически от
`RepositoryMetric`: stars и archive state имеют разную семантику, TTL, error
policy и consumer contract.

### 2. Внешнее evidence остаётся наблюдением

Worker делает public, conditional, bounded GitHub request. Catalog/API читает
последний сохранённый результат. `archived=true` создаёт только visible
warning/deprecation proposal. Ни API, ни web, ни worker не выставляют
`deprecated`, `blocked`, `component_verified` и не удаляют target автоматически.

Ограничение частоты, сбой, некорректный ответ, закрытый репозиторий и изменение
`repository identity` не заменяют последнее `good observation` и не превращаются в `archived`.

### 3. Account impact получает новую версию server contract

Локальные v1 schemas сохраняют `freshness=local_snapshot` и
`authority_boundary=local_registry`. Server не переиспользует эти значения для
account-wide данных.

Server projection получает отдельную versioned response family с явными:

- `authority_boundary=account`;
- source revision / snapshot timestamp;
- `freshness=account_snapshot`, `stale` или `unavailable`;
- read-only `action=none`;
- exact/estimated/unavailable measurement states.

Это позволяет CLI и web показывать один смысл, не ложно утверждая, что local
registry равен account-wide registry.

### 4. API остаётся единственной web/backend boundary

Web не читает PostgreSQL, GitHub или local CLI registry. Он использует
generated API client и shared parser/corpus. Публичный catalog получает
optional safe archive summary; impact/blast-radius resources требуют
authentication и account ownership checks.

Публичный маршрут `catalog` не выполняет сетевое обновление. `Refresh` —
ограниченная задача worker с идемпотентным key по `repository identity` и
`freshness window`.

### 5. Canonical copy и deep-link grammar не копируются

Python contracts остаются источником CLI copy templates и deep-link grammar.
Web получает generated projection либо build-time drift-checked artifact. Любая
ручная строковая копия команды, URL path, locale или report fragment считается
contract defect.

### 6. UI показывает происхождение и неопределённость

Archive status — отдельный external-evidence warning, не trust badge. Impact
panel показывает baseline, authority, freshness, exact/estimated/unavailable и
capability delta. Ни одна карточка не сворачивает эти факты в один score и не
предлагает destructive action.

Визуальная реализация остаётся в текущем ai_stp design system: semantic tokens,
existing card/detail/menu primitives, RU/EN parity, keyboard/focus support,
reduced motion и responsive Operate behavior. `$impeccable` shape brief и
acceptance checklist являются частью delivery plan, но не заменяют contract.

## Рассмотренные варианты

1. **Запрашивать GitHub из catalog request.** Отклонено: создаёт нестабильный
   TTFB, rate-limit coupling и недетерминированную публичную выдачу.
2. **Показывать CLI local registry в web.** Отклонено: web не имеет доступа к
   локальному файлу и это смешивает authority boundaries.
3. **Сложить archive state в `RepositoryMetric`.** Отклонено: stars и lifecycle
   evidence имеют разные TTL, history и error semantics.
4. **Изменить v1 impact schema на месте.** Отклонено: старый CLI contract
   перестанет честно описывать `local_snapshot`.
5. **Сделать web-only строковые команды и URL.** Отклонено: уже привело к
   drift и ломает `REQ-3009`/`REQ-3706`.
6. **Один общий risk score для impact/archive.** Отклонено: capability,
   external evidence и lifecycle policy принадлежат разным осям.

## Последствия

Положительные:

- web, CLI и API получают один проверяемый смысл без copy-paste contracts;
- public catalog остаётся быстрым и не зависит от GitHub availability;
- stale/unavailable evidence видны и не превращаются в ложное доверие;
- account-wide report имеет честную authority boundary;
- migration/rollback не меняют immutable catalog bytes.

Цена решения:

- добавляется server observation storage, migration и worker job;
- для отчёта impact нужен отдельный вариант ответа server и матрица API-тестов;
- generated web artifacts становятся обязательной частью `web-check`;
- UI должен поддерживать больше состояний, чем только ready/error.

## Rollout и recovery

1. Сначала добавить контракты, схемы, отрицательные fixtures и generated outputs.
2. Применить nullable observation migration; пустая таблица означает
   `unavailable`.
3. Запустить обновление worker для public GitHub coordinates с ограниченным retry.
4. Включить additive catalog field и web warning.
5. Включить impact v2 endpoint после account read-model tests.
6. При ошибке worker отключить refresh job, сохранив последний good snapshot.
   При ошибке projection вернуть явный `unavailable`, не скрывая catalog object.
7. При ошибке deployment откатить приложение по обычному runbook; observation
   history удалять нельзя.

## Условия пересмотра

Решение пересматривается при добавлении второго forge, credentialed/private
observation, org-wide roles, auto-lifecycle workflow, external tokenizer или
публичного report resource. Каждое такое изменение требует отдельного ADR и
новой версии затронутого machine contract.
