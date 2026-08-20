---
description: "Catalog QL, два режима пагинации и изолированные реакции."
last_verified: "2026-08-09"
---

# ADR-0073: Catalog query, pagination и reactions

Статус: принято.

## Контекст

Cursor-only каталог безопасен и подходит CLI, но web должен показывать число
результатов и страниц. Простая подстрока не выражает логические ограничения, а
клиентская-only валидация не защищает API. Сортировка по likes вводит социальное
состояние, ранее исключённое из MVP, и не должна смешиваться с trust evidence.

## Варианты

1. Заменить cursor offset/page пагинацией. Это ломает CLI и ухудшает стабильность.
2. Оставить cursor-only и вычислять страницы на клиенте. Точный total получить
   нельзя, а обход всех страниц дорог и нестабилен.
3. Поддержать взаимоисключающие cursor и page modes, единый AST и отдельный
   агрегат reactions.

## Решение

Выбран вариант 3. Catalog QL разбирается собственным bounded lexer/parser в
типизированный allowlisted AST. Структурные filters объединяются с AST через
`AND`. Обычная строка остаётся full-text term. Cursor mode сохраняет opaque
keyset semantics; page mode возвращает total только для уже разрешённой
публичной выборки. `cursor` и `page` несовместимы.

Публичная проекция хранит только неотрицательный агрегат `likes_count`, отдельно
от паспортов, verification, trust и support. Источник изменения individual
reactions не входит в это решение и не раскрывается через catalog API. `likes`
sorting имеет стабильный tie-breaker `updated_at, stable_id`.

## Последствия

OpenAPI и fixtures получают additive поля/parameters. Нужны индексы для
публичной проекции, фильтров, full-text/trigram search и reaction aggregate.
Count не должен включать hidden/private строки. Frontend parser является UX
помощью, но backend повторяет всю проверку. Любое расширение grammar требует
версии и golden corpus.

## Условия пересмотра

Решение пересматривается, если точный count не укладывается в performance budget,
если каталог переходит на внешний search engine либо социальная механика снова
исключается продуктовым решением.
