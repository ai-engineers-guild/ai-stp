---
description: "Активация и проверка GitHub-защит перед публичным выпуском."
last_verified: "2026-08-08"
---

# Защиты репозитория перед выпуском

## Источник политики

Ожидаемые настройки принадлежат файлу
`.github/release-protection-policy.json`. Он фиксирует:

- обязательные контексты `check` и `back-python-3.12` для `main`. Агрегатной
  job, сводившей их в один контекст, в дереве нет: она зависела от класса
  флота, который её не размещал, и стоила целого зелёного прогона
  (`ADR-0102`). Опасность, ради которой она существовала, сейчас не наступает —
  ни одна из двух job не пропускается условно, `back-python-3.12` несёт
  `if: !cancelled()`, а отменённый прогон не является кандидатом на слияние.
  Возврат агрегата — изменение и этого файла, и `check.yml` одним действием:
  контрактный тест требует, чтобы каждый требуемый контекст был именем
  существующей job;
- актуальные ревью, одобрение после последнего push и разрешение обсуждений;
- применение правил к администраторам, запрет force-push и удаления веток;
- required reviewers для `pypi`;
- только tag `v*` для `pypi`;
- ruleset, запрещающий удаление и non-fast-forward изменение release tags.

Названия status checks проверяются против канонического workflow контрактным тестом.
Копия настроек в этом runbook вторым источником истины не является.

## Предварительные условия

1. Репозиторий публичен либо тариф действительно поддерживает protections.
2. Точные release-candidate SHA и tag согласованы, полный `just check` зелёный.
3. Физически отдельные CI, deploy, release-build и release-attest runners
   зарегистрированы и не делят пользователя, host, файловую систему и network
   authority.
4. Владельцы `pypi`, required reviewers и аварийный порядок доступа
   согласованы.
5. Получено отдельное разрешение на изменение GitHub settings. Этот runbook сам
   ничего не меняет.

## Порядок активации

1. Включить protection для `main` по policy-файлу. Отдельной интеграционной
   ветки нет: линия одна (`docs/engineering/git-workflow.md`).
2. Создать environment `pypi`, добавить required reviewer и custom deployment
   policy типа tag с pattern `v*`. Постоянные PyPI secrets не добавлять.
3. Создать активный tag ruleset для `refs/tags/v*`, запрещающий deletion и
   non-fast-forward update.
4. Настроить PyPI Trusted Publisher на точные owner/repository/workflow/environment
   только после отдельного разрешения на публикацию.

Environment нельзя сначала «упомянуть» из workflow: GitHub может создать пустой
Такой environment не имеет reviewer и deployment policy. Сначала настройки, затем
workflow.

## Read-only проверка

```bash
just release-protections
```

Команда читает настройки через `gh api`, не выполняет `PUT`, `POST`, `PATCH` или
`DELETE` и завершается отказом при `403`, `404`, отсутствующем поле или несовпадении.
Для доказательства exact release сохранить нормализованный снимок:

```bash
uv run python release_scripts/verify_protections.py \
  --write-snapshot protection-evidence.json
```

Снимок содержит только настройки и ошибки API, но всё равно проверяется перед
публикацией на отсутствие неожиданной информации. Сам файл не коммитится как
«живое» состояние: evidence прикрепляется к точному release run.

## Отрицательная проверка и откат

- Временный test tag вне `v*` не получает полномочие `pypi`.
- Попытки force-push/delete для защищённых refs отклоняются GitHub.
- PR без обоих checks, актуального approval или закрытых обсуждений не сливается.
- При ошибочной настройке publication и deployment workflows блокируются до
  восстановления policy; защиты не ослабляются ради завершения выпуска.
- Уже опубликованные PyPI bytes не заменяются. Используется yank/новая patch version
  по runbook `pypi-release.md`.

Issue `#188` закрывается только по успешному live-отчёту на публичном release SHA,
наблюдаемым отрицательным попыткам и настройкам protected environments.
