---
description: "Решение хранить публичные документы и политики ревизиями с репозиторным импортом."
last_verified: "2026-08-08"
---

# ADR-0070: Версионированные публичные документы и политики

Статус: принято.

## Контекст

Сайту нужны технические документы для людей и agents, а также privacy, cookie,
service и author-content/license policies. Файлы repository — лучший источник
технической документации, но website должен уметь служить неизменяемую
локализованную revision через API и хранить policy texts отдельно от deploy.

## Варианты

1. Рендерить `docs/**` файловой системой Next.js. Нет API, version history,
   locale lifecycle и policy draft/publish.
2. Сделать свободный CMS. Расширяет attack/authoring surface без MVP need.
3. Ввести platform-owned immutable PublicDocument revisions, импортируемые из
   разрешённых закреплённых источников repository или публикуемые служебным процессом.

## Решение

Принимается вариант 3 по SPEC-031. Technical docs остаются canonical в Git;
CI import записывает exact source commit/path/digest в platform revision. Policies
имеют staff-controlled drafts/publish/supersession. Public web/API читают только
published localized revisions через shared safe Markdown renderer.

## Последствия

- Нужны document/revision storage, API, import job, public cache policy,
  operator workflow и migration/archive tests.
- Web не тянет Markdown по произвольному URL и не является Git client.
- Будущее обязательное acceptance policy потребует отдельного ADR и auditable
  account acceptance record.
- Глобальная 500 страница и 404 являются частью public shell, а не policy CMS fallback.

## Условия пересмотра

Решение пересматривается при появлении multi-repository docs federation,
enterprise legal tenancy или обязательного электронного согласия с policy.
