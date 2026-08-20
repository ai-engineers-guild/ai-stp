---
description: "Поля машинного документа web, парные URL и запрет утечек."
last_verified: "2026-08-16"
---

# Machine-проекция web

Владелец требований — `SPEC-036`. Этот документ фиксирует машинные поля,
парные URL и запрещённые классы данных. Состав пунктов навигации и тексты
страниц сюда не входят.

## Парный URL

| Проекция | Path |
|---|---|
| human | `/{locale}/{path}` |
| machine | `/{locale}/ai/{path}` |

`locale` — `en` или `ru`. Query string принадлежит паре и не нормализуется
отдельно. Эндпоинты API, `/llms.txt`, `/llms-full.txt`, `/agents.md` и внешние
URL не являются страницами и не переписываются.

## Запись inventory

| Поле | Форма |
|---|---|
| `pattern` | сегменты human-пути; `:name` — один сегмент, `*` — хвост |
| `access` | `public` или `session` |
| `feature` | optional compiled feature key |
| `envGate` | optional runtime gate той же human-страницы |
| `presenter` | `domain` или `generic` |

Каждый `page.tsx` human-дерева имеет ровно одну запись. Страница без записи
является дефектом.

## Документ объекта

Обязательные поля компонента: `stable_id`, `version`, `digest`, `harness`,
`component_type`, `trust_lane`, `author_verified`, `component_verified`,
команда установки CLI. `component_type` принимает только
`instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`.
Сетап вместо `component_type` отдаёт `purpose` и `target_role`.

## Запрещённые классы

В документ не входят адреса медиа, `avatar`, `CSRF`, токен сессии, секрет,
пароль, внутренний идентификатор операции и декоративные поля, которых нет
в человеческих фактах той же страницы тому же субъекту.
