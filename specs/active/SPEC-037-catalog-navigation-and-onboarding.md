---
description: "SPEC-037: Компактный каталог, owner/public navigation и CLI onboarding."
last_verified: "2026-08-17"
---

# SPEC-037: Каталог, навигация и CLI onboarding

## Цель

Каталог остаётся быстрым и понятным: поиск всегда виден, фильтры не занимают
страницу, применённые ограничения понятны и обратимы. Владелец безопасно
переходит между своим object workspace и public view, а пустые экраны объясняют
следующее действие через CLI.

## Границы

Входят: уточнение выдачи без потери поиска, chips, reset, подсказка справки,
выбор нескольких тегов, owner/public navigation, копирование CLI-команд и empty states. Не входят: browser
редактор паспортов, клиентская authorisation, рекомендации и скрытые фильтры.

## Термины

- `Owner view` — авторизованная проекция объектов текущего account.
- `Public view` — анонимная проекция опубликованного каталога.
- `Applied filter` — фильтр в URL, применённый серверным контрактом.
- `Refinement surface` — responsive оболочка дополнительных ограничений выдачи;
  форма оболочки может отличаться по viewport, но controls и semantics одинаковы.

## Требования

- `REQ-3701`: В hero каталога находятся ровно две компактные icon-кнопки:
  текстовый поиск и фильтры/сортировка. Выбор типа выдачи (`components`,
  `setups`, Both/All) находится в панели фильтров. Дополнительные ограничения
  открываются по запросу, не занимают постоянную площадь страницы и на узком
  viewport не вытесняют результаты: пользователь видит те же controls, может
  закрыть уточнение с клавиатуры и видит число уже применённых фильтров.
  Реализация не обязана быть одним конкретным `modal`/`drawer`, но обязана
  сохранять searchable multiselect и date/sort/view controls из текущего
  контракта.
- `REQ-3702`: Фильтр тегов поддерживает все значения, разрешённые контрактом, а не
  только первый tag. Применённые filters отображаются dismissible chips и
  сериализуются в URL без потери порядка/повторов; `Reset all` возвращает
  контрактные defaults.
- `REQ-3703`: Элемент справки рядом с filters объясняет каждый filter, trust lanes,
  request-scoped experimental consent, cursor pagination и page-mode totals, если
  они доступны. Это semantic button/dialog с keyboard/focus support, а не
  hover-only tooltip.
- `REQ-3704`: Experimental consent остаётся отдельным явным запросом и не
  сохраняется как бессрочная preference. UI не смешивает experimental results с
  authoritative results.
- `REQ-3705`: Owner version с public state показывает `View public page`; public
  object/version page показывает `Manage this version` только авторизованному
  владельцу. Для закрытого черновика используются маршруты предварительного просмотра владельца, а не публичные ссылки.
- `REQ-3706`: Каталог и страницы владельца дают действие копирования для точных CLI-команд
  (`registry show` для public object/version и owner-appropriate next step),
  и берут шаблон команды из одного канонического источника. UI не обещает browser install.
- `REQ-3707`: Пустые owner objects/access/publications states объясняют, что
  паспорта и setup создаются CLI/agent, дают copyable safe command и ссылку на
  документацию. Они не показывают несуществующую browser-edit функцию.
- `REQ-3708`: Mobile primary navigation имеет menu/drawer и не скрывает signed-in
  маршруты без альтернативы. Активный маршрут, текущее состояние и keyboard focus видимы.

## Состояния и ошибки

Некорректный URL-фильтр получает текущее типизированное состояние validation без молчаливого
drop. Network error сохраняет видимые applied filters и предлагает повтор. Copy
failure сообщает результат без ложного success. Owner/public link при изменении
lifecycle показывает safe not-found/error state.

## Безопасность и приватность

URL, chips и help не раскрывают закрытые IDs, согласие или существование private
objects. Owner navigation проверяется API/server session, а не hidden button.
CLI-команды экранируют arguments и не содержат token, local path или secret.

## Совместимость и миграция

Существующие query parameters сохраняют значение. Новый UI не декодирует cursor;
Форма фильтра принадлежит current OpenAPI contract. Help text локализован и не
дублирует нормативные правила trust model.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-3701`–`REQ-3703` | Component/a11y tests покрывают responsive refinement surface, открытие/закрытие на narrow viewport, chips, multi-tag, сохранение searchable controls и Reset all; `mobile-public-smoke.spec.ts` подтверждает keyboard/focus на 360 и 430 px в `ru` и `en`. |
| `REQ-3702` | Проверка URL доказывает сохранение всех выбранных tags, порядка и сброса к contract defaults. |
| `REQ-3704` | Browser test доказывает отдельные experimental section и отсутствие persisted consent. |
| `REQ-3705` | Owner/outsider matrix доказывает public manage link и private preview redaction. |
| `REQ-3706`–`REQ-3707` | Tests сверяют copied command с canonical source и empty-state links. |
| `REQ-3708` | Mobile browser/a11y test проходит все signed-in routes через navigation; `mobile-public-smoke.spec.ts` подтверждает keyboard/focus mobile nav на 360 и 430 px в `ru` и `en`. |
