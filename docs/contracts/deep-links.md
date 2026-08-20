---
description: "Грамматика канонических URL и CLI references для component, setup, publisher и report intent."
last_verified: "2026-08-15"
---

# Канонические CLI/web deep links

Владелец требований — `SPEC-030`, решение — `ADR-0064`. Этот документ фиксирует
машинную grammar `deep_link_v1`.

## Нормализованный target

| Поле | Форма |
|---|---|
| `grammar_version` | `1` |
| `kind` | `component`, `setup` или `publisher` |
| `stable_id` | canonical ID с prefix, соответствующим `kind` |
| `version` | optional exact canonical `X.Y`; только component/setup |
| `locale` | `ru` или `en`; default `ru` |
| `intent` | `view` или `report`; `report` требует component/setup и version |

## URL paths

```text
/{locale}/catalog/components/{component_id}
/{locale}/catalog/components/{component_id}/versions/{X.Y}
/{locale}/catalog/setups/{setup_id}
/{locale}/catalog/setups/{setup_id}/versions/{X.Y}
/{locale}/publishers/{account_id}
```

`report` использует exact component/setup version path и фиксированный fragment
`#report`. Query отсутствует во всех формах. Base address — действующий
`catalog.url` без `/v1`; его необязательный базовый путь сохраняется перед маршрутом.

## Ссылка CLI

Каноническая форма — массив аргументов, а не shell-строка:

```json
[
  "ai-stp", "link", "web",
  "--kind", "component",
  "--id", "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  "--version", "1.2",
  "--locale", "ru",
  "--json"
]
```

Для `report` перед `--json` добавляется `--report`. Human `cli_command` получается
только соединением безопасных элементов канонического массива пробелом. Опускание
`--locale` разрешено на входе CLI, но canonical output всегда включает resolved
locale.

## Валидация и доступ

Stable ID и версия проверяются до построения URL. Parser принимает только точно
настроенные схему, authority и базовый путь, перечисленные пути и fragment `report` в
допустимом контексте. Credentials, query, кодированные разделители, лишние сегменты
и неизвестные fragments отклоняются.

Генерация и разбор ничего не читают из каталога. Ссылка не является доказательством
существования или доступа: публичность, private authorization и запрет перечисления
остаются за существующей границей web/API.

Web-потребитель использует тот же packaged corpus и ту же grammar. Он не
является вторым владельцем маршрутов.
