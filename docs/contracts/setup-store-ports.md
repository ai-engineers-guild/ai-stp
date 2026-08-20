---
description: "Контракт локального обнаружения, preview и импорта компонентов из SX и APM."
last_verified: "2026-08-13"
---

# Local setup-store ports

## Команды

`registry port discover --root <path>` находит поддерживаемые manifests.
`registry port inspect --adapter sx|apm --root <path>` показывает conversion
report. `registry port plan` добавляет exact digest и последствия операции.
`registry port import` требует тот же root/adapter, `--expected-plan-digest` и
`--confirm`; его единственный эффект — local registry write.

Флаги и result schemas принадлежат генерируемому `help --agent`, поэтому здесь
не дублируются. Внешний store и harness target остаются byte-identical. Port не
вызывает vendor CLI, package manager, Git или сеть.

## Общая модель

Descriptor фиксирует `setup-store-port/1`, адаптер, прочитанную версию контракта,
manifest, доменно-разделённый snapshot digest и наличие необязательного vendor CLI.
Каждая mapping-запись сохраняет внешние identity/type/version, source coordinate,
доступный digest источника, канонический вид компонента, локальный путь, пропуски и
ограниченные metadata. Неизвестные поля перечисляются JSON-path-подобными указателями;
они не влияют на паспорт скрытым образом.
Для доступного local path inspection дополнительно строит content digest теми же
bounded правилами, которыми последующий import прочитает artifact. Поэтому plan
меняется не только вместе с manifest, но и при изменении фактических bytes.

Plan содержит весь inspection, conflicts и пять явных trust consequences:
объект остаётся local-only, обе verified-оси ложны, внешний store и target не
изменяются. Collision external identities закрывает apply. Повторный import
одного adapter/snapshot/external identity возвращает ранее созданные stable и
revision identifiers.

## SX schema 2

Источник структуры — закреплённый
[manifest spec](https://github.com/sleuth-io/sx/blob/a74798be061fb125b0748f083f0418e058978a13/docs/manifest-spec.md).
Port принимает только локальный `source-path`, остающийся внутри root. `source-http`
и `source-git` показываются с координатой/digest, но offline import их не скачивает.
`rule` становится `instruction`, а `claude-code-plugin` и `app-plugin` — `plugin`;
остальные шесть общих названий совпадают. Collection сохраняется в report как
omission: одно имя участника не является exact Component version/digest, поэтому
из него нельзя честно построить Setup passport.

## APM lock 1/2

Источник структуры — закреплённая
[lockfile implementation](https://github.com/microsoft/apm/blob/3aa0365540e3d9ef4685740cea6a09094ff35377/src/apm_cli/deps/lockfile.py).
Port группирует только declared `deployed_files` по известным границам `skills`,
`agents`, `prompts`/`commands`, `hooks`, `plugins`, `instructions`/`rules` и
`mcp`. `prompt` соответствует каноническому `command`. Нераспознанный deployed
path не создаёт компонент; package type сам по себе не используется для
угадывания содержимого.

## Ограничения и отказ

Manifest — один regular non-linked UTF-8 файл не больше 4 MiB; максимум 1000
records и 100 показанных unknown-field указателей; при превышении report явно
показывает исходное и отображённое количество. YAML duplicate keys запрещены. Root не
может быть home, относительный source не может быть абсолютным, содержать `..`
или выйти из root после разрешения пути. Несовместимая schema получает отдельный
отказ, а отсутствие vendor CLI не мешает offline inspection/import.
