---
title: "Публикация"
description: "Как авторы публикуют компоненты и сетапы в ai_stp."
---

# Публикация

Публиковать компоненты и сетапы может любой пользователь. Предварительной
модерации публикаций в MVP нет, но происхождение, права и проверки остаются
видимыми.

Публичная версия должна происходить из публичного GitHub-репозитория с точным
commit и подпутём. После публикации версия неизменяема. Номер версии — `X.Y`,
а не SemVer: поля patch нет, перезаписать `1.0` нельзя.

Автор может быть подтверждён платформой, но это подтверждает происхождение, а
не безопасность содержимого. Как готовить дерево:
[Авторство](authoring.md).

Публикация — CLI-путь со входом в аккаунт. Веб может показать результат; он
не привязывает байты и не подтверждает hash плана.

## Предусловия

1. Есть локальная идентичность устройства: `ai-stp device init --json`.
2. Вы вошли на том же устройстве: `ai-stp auth status --json`.
3. Объект принят, паспорт проходит validate, локально выпущен `X.Y`.
4. Публичный источник — точный GitHub commit. Ветки и короткие SHA
   отклоняются.
5. Секреты, приватные пути и тела `.env` отсутствуют в паспорте и артефакте.

```bash
ai-stp component passport validate --id <stable_id> --json
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию вместо следующего минора.
Мажорная линия — отдельная граница доступа.

## Подпись attestation (необязательно, точно)

Если есть тестовые доказательства, зависящие от учётных данных, подпишите их
ключом активного устройства **до** плана публикации. Файл должен быть новым;
существующий путь отклоняется.

```bash
ai-stp attestation sign \
  --id <stable_id> \
  --version 1.0 \
  --check-id <check_id> \
  --policy-version <policy> \
  --tool-version <name>=<version> \
  --harness-id <harness> \
  --harness-version <version> \
  --provider-version <version> \
  --test-case-id <case> \
  --result passed \
  --output ./attestation.json \
  --confirm \
  --json
```

`--result` — `passed` или `failed`. `--tool-version` и `--test-case-id` можно
повторять. Имена инструментов, похожие на секрет, отклоняются.

## Публикация выпущенного компонента

Спланируйте, просмотрите, затем подтвердите **точный** hash, который вам
показали. Если ответ confirm потерялся, это не второй confirm: сначала
прочитайте status.

```bash
ai-stp publication plan \
  --id <stable_id> \
  --version 1.0 \
  --attestation-file ./attestation.json \
  --json

ai-stp publication status --plan-id <plan_id> --json

ai-stp publication confirm \
  --plan-id <plan_id> \
  --plan-hash <plan_hash> \
  --confirm \
  --json
```

`--attestation-file` повторяемый и необязательный. Создание плана само по себе
не публикует. Ошибка проверки не должна оставлять частично опубликованную
версию.

## Извлечь embedded-компонент и опубликовать его

Компонент, который живёт только внутри сетапа, можно поднять в обычный план
публикации:

```bash
ai-stp component publish \
  --from-setup <setup_id> \
  --setup-version 1.0 \
  --component-id <component_id> \
  --json
```

Команда материализует участника и создаёт обычный план публикации. Его
подтверждают через `publication confirm`, как выше.

## Публикация сетапа и всех pin

Сетап не может стать публичным раньше своих точных pin. `setup publish` — это
**набор**: по одному плану на каждый ещё не публичный pin, затем план самого
сетапа. Уже публичные участники перечисляются и не планируются заново.

```bash
ai-stp setup publish plan --id <setup_id> --version 1.0 --json

ai-stp setup publish confirm --set-digest <set_digest> --confirm --json
```

Confirm идёт по участникам в порядке набора: сначала компоненты, затем сетап.
Отказ останавливает подтверждение и переводит набор в `partial`.
Опубликованные участники остаются опубликованными; повторный
`setup publish plan` помечает их как already published.

Если ответ confirm потерялся:

```bash
ai-stp publication status --plan-id <plan_id> --json
```

Не выдумывайте второй confirm, чтобы узнать исход.

## Проверки

Публикация проходит проверку паспорта, формата, совместимости и доступности
source. Обязательные safety-сканы, которые провалились или не запустились,
блокируют публикацию. Что означает процент карточки:
[Проверки безопасности](../security-checks.md).

## Жалобы

Проблемный объект можно пожаловаться из веба или CLI. Жалоба создаёт закрытый
случай модерации, а не публичное обсуждение.

```bash
ai-stp report preview --kind component --id <id> --version 1.0 --content-digest sha256:... --json
ai-stp report confirm --plan-id <id> --plan-digest <digest> --confirm --json
ai-stp report list --json
```

Подробности: [Жалобы](../cli/report.md).

## Связанные страницы

- [Авторство](authoring.md) — как подготовить дерево.
- [Публикация компонента](../cli/component-publish.md) — adopt, release, plan.
- [Publication](../cli/publication.md) — attest, plan, confirm.
- [Веб-публикация](../web/publications.md) — подтвердить план, собранный CLI.
- [Проверки безопасности](../security-checks.md) — обязательные сканы, которые
  блокируют.
- [Доверие и безопасность](../trust-and-safety/index.md) — происхождение — не
  безопасность.
