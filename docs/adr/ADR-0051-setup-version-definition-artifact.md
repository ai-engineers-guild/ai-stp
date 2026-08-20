---
description: "Независимый definition artifact и полный паспорт подтверждённой SetupVersion."
last_verified: "2026-08-09"
---

# ADR-0051: Артефакт определения SetupVersion

Статус: принято.

## Контекст

Подтверждение предложения создавало общий `PassportEnvelope` только с `facts`, хотя
`SetupVersion` по публичной схеме обязана иметь `SetupVersionPassport`: точные ссылки
на компоненты, версию, назначение, агрегированные требования, лицензию и
`ArtifactRef`. Bundle принимал общий envelope как паспорт, поэтому локальная версия
не соответствовала собственной generated schema.

Использовать HarnessBundle как `artifact` паспорта нельзя. ZIP содержит
`setup-passport.json`; если паспорт содержит digest этого ZIP, digest зависит от
самого себя и не вычисляется без фиксированной точки. Подстановка `bundle_digest`
также смешала бы домены `artifact` и `bundle`.

## Решение

Явное confirmation создаёт отдельные канонические bytes формата
`ai-stp-setup-definition/1`. Определение содержит:

- stable ID и `X.Y` SetupVersion;
- один `harness_id`;
- selection input digest;
- отсортированные exact component refs с passport digest.

Bytes сериализуются RFC 8785, получают доменно разделённый digest
`ai-stp:artifact:v1` и сохраняются в immutable SQLite content store в той же
транзакции, что entity, revision, version, RecommendationTrace и pin. Полный
`SetupVersionPassport.artifact` указывает на эти bytes и размер. В паспорт также
входит `artifact_format=ai-stp-setup-definition/1`.

HarnessBundle является последующей нативной компиляцией. Он включает неизменяемый
паспорт, отчёты и managed files, имеет собственный logical `bundle_digest` и raw
SHA-256 ZIP bytes. Ни один из его digest не подменяет `ArtifactRef` SetupVersion.

## Полнота метаданных

Если каждая ссылка на компонент разрешается в полный `ComponentVersionPassport`,
версия сетапа агрегирует обязательные переменные окружения, учётные данные,
авторизацию, разрешения, внешние точки доступа и лицензию. Порядок и дедупликация
детерминированы.

Исторические локальные компоненты могут иметь только общий envelope. Такая частная
SetupVersion сохраняется с `member_metadata_complete=false`, консервативной частной
составной лицензией и `redistribution_allowed=false`. Этот признак является
обязательным блокером публикации; локальные composition/provider checks продолжают
читать точные component revisions и не считают неполный aggregate разрешением.

## Атомарность и совместимость

Definition bytes записываются внутри `BEGIN IMMEDIATE`. Сбой после записи content
row откатывает её вместе с revision/version/trace/pin; авторитетного осиротевшего
artifact не остаётся. Повтор confirmation возвращает уже созданную неизменяемую
версию и не строит новый definition.

Ранее созданные локальные SetupVersion не переписываются: изменение immutable
passport задним числом нарушило бы точные ссылки. Новый confirmation всегда создаёт
полный паспорт. Публичная публикация старой общей формы требует явного нового
version/fork, а не скрытой миграции digest.

## Последствия

SetupVersion и HarnessBundle больше не образуют цикл хэшей, локальный объект проходит
формальную passport schema, а artifact можно синхронизировать независимо от
конкретного provider conversion. Цена — отдельная небольшая content row и явный
publication blocker для legacy metadata.
