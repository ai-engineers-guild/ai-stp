---
description: "Решение: web deploy-поверхности управляются build-time Git/YAML profiles."
last_verified: "2026-08-12"
---

# ADR-0089: Build-time web feature profiles

Статус: принято.

## Контекст

Issues `#267` и `#284` требуют отключать целые web-поверхности из routes,
навигации, карте сайта, машинной проекции и по возможности клиентских пакетах. Веб-приложение уже
использует Next.js App Router, standalone image и отдельные human/machine route trees.
Runtime-флаг не может одновременно изменить уже собранный client bundle, сохранить
static generation и гарантировать одну идентичность artifact.

## Варианты

1. Внешняя платформа флагов. Даёт выбор аудитории и аудит, но добавляет сервис, SDK,
   failure modes и dependency без потребности MVP.
2. Runtime env/config endpoint. Позволяет менять флаг без build, но оставляет код в
   артефакт, создаёт расхождение гидратации и кеша и переводит статические страницы в
   dynamic rendering.
3. Versioned YAML profiles, разрешаемые при build. Просты, Git-native, проверяемы,
   совместимы с standalone artifact и дают bundler literal constants.

## Решение

Принимается вариант 3. TypeScript registry владеет ключами и metadata; YAML владеет
полными значениями профиля. Профиль и булевы переопределения читаются только при сборке.
Неизвестная или неполная конфигурация немедленно отклоняется. Результат встраивается как константы и
является частью идентичности image.

Флаг функции не является проверкой полномочий. Человеческие и машинные маршруты проверяют один собранный
set; navigation, SEO и machine discovery являются проекциями тех же route/feature
annotations. Профили `public_saas` и `self_hosted` являются полными продуктовыми
наборами. Ключи `content_hub` и `saas_public_pages` управляют материалами и
SaaS-служебными страницами; новые keys добавляются только вместе с реальным consumer
и тестом.

Content hub использует repository Markdown и существующий Fumadocs local source,
без внешней CMS. Locale fallback отсутствует: RU/EN entries образуют строгие пары.

## Последствия

- Для разных profiles собираются разные точные web images.
- Изменение profile требует rebuild/redeploy, зато artifact детерминирован.
- Оперативное аварийное выключение, группы пользователей и удалённый провайдер откладываются до доказанной нужды и
  потребуют нового ADR.
- Every new route обязан аннотировать feature в human/machine/discovery projections.
- Build matrix и scenario tests становятся release evidence.

## Условия пересмотра

Решение пересматривается, если доказана операционная потребность выключать поверхность
без rebuild быстрее допустимого rollback либо появляются per-request cohorts. Тогда
структурные флаги сборки сохраняются, а оперативные флаги вводятся отдельной
категорией, не обещающей bundle exclusion.
