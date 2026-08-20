---
description: "Fail-closed происхождение установленных GitHub-компонентов из ограниченной цепочки manifest-доказательств."
last_verified: "2026-08-09"
---

# ADR-0055: Точное происхождение установленных компонентов

Статус: принято.

## Контекст

Путь в cache не доказывает источник компонента. Имя каталога можно подделать,
Git remote может содержать credential, а запуск Git или harness во время
read-only discovery расширяет исполняемую и побочную поверхность. В то же время
issue `#231` требует находить глобальные компоненты из GitHub с устойчивой
идентичностью и происхождением.

Claude Code хранит установленные plugins в versioned cache, различает источник
marketplace и источник plugin и копирует установленные байты в
`~/.claude/plugins/cache`. Относительный plugin source принадлежит repository
marketplace, а отдельные `github`, `url` и `git-subdir` источники могут иметь
собственный exact SHA.

## Решение

CLI использует отдельный bounded source adapter. Для Claude Code он связывает:

1. поддерживаемый ledger `installed_plugins.json` версии 2;
2. `known_marketplaces.json` с GitHub `owner/repo`;
3. manifest по вычисленному пути
   `plugins/marketplaces/<name>/.claude-plugin/marketplace.json`;
4. запись plugin с allowlisted source-kind;
5. существующий install path строго внутри
   `plugins/cache/<marketplace>/<plugin>`;
6. полный 40-символьный commit SHA.

Поле `installLocation` не используется. Adapter не запускает Git или harness, не
ходит в сеть, не принимает URL с userinfo, не отражает содержимое manifest или
системный текст ошибки. Каждый manifest ограничен четырьмя MiB. Floating ref без
наблюдаемого exact commit не становится точным происхождением.

GitHub-находка получает `provenance.kind=github`, `state=exact`, канонический
HTTPS repository, revision, необязательный subpath, package name/version и
закрытый список видов evidence. Обычная layout-находка получает только
`filesystem/local`. Установленный plugin без доказанного GitHub source остаётся
видимым как `package/observed` с package name/version, но без repository и
revision. Несогласованные сочетания отклоняются машинной схемой.

Ошибочный, неизвестной версии или неполный manifest не угадывается. Команда
возвращает безопасный diagnostic code и продолжает независимое layout-discovery.
Project/local scope из глобального installation ledger не повышается до global.

При явном принятии точные `repository`, `revision`, `subpath` и идентичность
пакета сохраняются в паспорт вместе с `content_digest`. `candidate_id` включает
происхождение; изменение source evidence создаёт другого кандидата, но не меняет
уже созданный логический Component.

## Последствия

- глобальный GitHub plugin можно безопасно адресовать и принять без догадки по
  имени каталога;
- служебные buckets `plugins/cache`, `data` и `marketplaces` больше не выдаются
  как отдельные plugins;
- неизвестный новый ledger требует явного обновления adapter и fixtures;
- точное npm/archive/Pi package происхождение требует отдельных adapters;
  наблюдаемая установка остаётся видимой, но не маскируется под GitHub;
- provenance доказывает заявленную цепочку установки, но не является platform
  attestation качества или безопасности кода.

## Условия пересмотра

Решение пересматривается при документированном versioned API installed plugins,
изменении cache layout или появлении подписанного installation manifest,
позволяющего заменить внутренний ledger более сильным доказательством.
