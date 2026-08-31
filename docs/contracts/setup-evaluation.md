---
description: "Машинный контракт профиля, плана и результата локальной оценки точного SetupVersion."
last_verified: "2026-08-31"
---

# Оценка точного сетапа

Владелец требований — [SPEC-040](../../specs/active/SPEC-040-setup-evaluation-profiles.md).
Этот документ фиксирует машинную границу команд `eval` и смысл их результата.

## Объекты

`SetupEvalProfile` версии `setup-eval/1` описывает намерение оценки независимо
от конкретного сетапа. В нём находятся scope, набор component types,
preconditions, checks, assertions, tolerances, budgets, isolation requirements
и `eval_permissions`. Полномочия оценки не наследуются от провайдера.

`SetupEvalPlan` связывает профиль с одним exact `SetupVersion`: setup и component
версии, passport/artifact digests, harness/provider/runner versions и timestamp.
`plan_digest` вычисляется по каноническому содержимому. При subset-eval каждый
component обязан входить в названный setup graph.

`SetupEvalResult` содержит полный план, результаты checks, точный runner,
`result_digest` и timestamp. `immutable_published_bytes_changed=false` и
`provider_permissions_used=false` являются частью строгого результата, а не
описательным обещанием.

## Команды

- `eval profile [--type <type>]` — показать reference profile без записи;
- `eval plan --setup-id ... --setup-version ... --harness-version ... --provider-version ... --runner-version ...` — сохранить content-addressed plan; повторяемый `--component-id` ограничивает scope;
- `eval run --plan-id ... --expected-plan-digest ...` — выполнить доступный
  локальный deterministic subset; exact digest является подтверждением;
- `eval status --run-id ...` и `eval show --run-id ...` — прочитать immutable evidence без повторного исполнения.

## Честное отсутствие runner

Core не вызывает модели и не выдаёт human review за автоматическую проверку.
Reference profile объявляет эти проверки, чтобы координаты будущего evidence
были стабильны, но локальный runner отвечает `not_run`. Поэтому такой результат
имеет `degraded`, а не `passed`. `failed` имеет приоритет над `degraded`.

Текущий `local_static` проверяет exact passport/artifact coordinates и
type-specific declared native surface. Он не исполняет артефакт и не является
доказательством функциональной корректности, безопасности или trust lane.
