---
description: "Точное происхождение Pi Git packages из объявленного глобального cache без чтения пользовательских настроек и запуска Git."
last_verified: "2026-08-09"
---

# ADR-0056: Происхождение Pi Git packages из cache

Статус: принято.

## Контекст

Pi документирует глобальные Git packages в
`~/.pi/agent/git/<host>/<path>` и закрепляет checkout на ref или commit.
`settings.json` одновременно является общим файлом настроек и может содержать
не относящиеся к discovery чувствительные значения. Читать его целиком ради
одного массива packages противоречит границе read-only discovery.

Запуск `git` также не нужен: он расширил бы исполняемую поверхность и мог бы
наследовать пользовательскую конфигурацию. Для происхождения достаточно
объявленного cache layout и точного Git `HEAD`.

## Решение

Source adapter ограниченно перечисляет только три уровня под `git/`:
host, owner и repository. Он не следует символическим ссылкам и закрывается
отказом при превышении лимита entries или ошибке чтения. Exact GitHub
provenance создаётся только для host `github.com`, валидных owner/repository
segments и checkout с безопасным точным `HEAD`.

`HEAD` читается как detached 40-символьный SHA либо как безопасная ссылка
`refs/heads/*`/`refs/tags/*`. Revision берётся из bounded loose ref или
`packed-refs`. Adapter не читает рабочие файлы, Git config, credentials и
`settings.json`, не запускает Git, package code, hooks или сеть.

Находка получает `github/exact`, канонический HTTPS repository, checked-out
revision, package identity и evidence `pi:git-cache-layout` плюс
`git:checked-out-head`. Это доказывает источник наблюдаемого checkout, но не
утверждает, что package включён текущим settings, чист относительно index или
подтверждён платформой.

Не-GitHub host не получает ложный GitHub claim. Повреждённый или floating
checkout не исчезает из обычных объявленных Pi layouts, но cache package не
выдаётся как exact и сопровождается безопасной диагностикой.

## Последствия

- глобальный Pi Git package имеет устойчивую source identity без доступа к
  общим пользовательским настройкам;
- loose и packed refs дают одинаковый результат;
- enabled/disabled state намеренно не угадывается;
- пакеты npm требуют отдельного адаптера `package/observed` без утверждения об
  источнике GitHub;
- изменение устройства cache или контракта хранения Git требует пересмотра
  адаптера.

## Условия пересмотра

Решение пересматривается при появлении отдельного подписанного installation
ledger Pi, документированного изменения cache layout или необходимости
доказывать чистоту всего checkout относительно Git index.
