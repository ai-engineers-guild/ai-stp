---
title: "Вход"
description: "Начать и завершить вход на платформу, посмотреть сессию, выйти и напечатать канонические ссылки на веб."
---

# Вход

Для локальной работы аккаунт не нужен. Вход нужен для частных
объектов, синхронизации, публикации, устройств на сайте и доступа.

Повседневная работа с аккаунтом — intent `account`. Движок drain'ит
device-code login и явный sync in-process. Не набирайте `auth login`,
если вы не восстанавливаете незавершённый device code.

```bash
ai-stp task start --intent account --idempotency-key account-session-01 --json
```

Следуйте `continuations`. Выполняйте `argv` только когда `actor` — `cli`.
Заблокированный вопрос authorization — `actor=external`: покажите код
один раз и остановитесь. Expert login / complete / logout ниже — для
операторов, у которых уже есть незавершённый код.

CLI запускает device-code flow, печатает код, который человек должен
одобрить, и сохраняет учётные данные только после этого одобрения.

`link web` на этой странице, потому что это круговой путь между
объектом каталога и сайтом. Он не входит в аккаунт. Это чтение.

## Команды

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp task start --intent account` | `apply` | `none` | повседневный вход и явный sync |
| auth login | `apply` | `none` | expert: начать вход и сообщить код, который пользователь должен одобрить |
| auth complete | `apply` | `none` | expert: завершить ожидающий вход, когда пользователь его одобрил |
| auth logout | `apply` | `none` | expert: закончить облачную сессию на сервере и здесь, сохранив все локальные данные |
| `ai-stp auth status` | `read` | `none` | сообщить связь с платформой: только локально, authenticated, expired или revoked |
| `ai-stp link web` | `read` | `none` | напечатать канонический веб-URL и обратимую ссылку CLI |

`auth login` записывает незавершённую авторизацию — устойчивое
состояние. `auth complete` сохраняет учётные данные и заново берёт
владение локальными паспортами. `--confirm` ни на одной из них нет:
решение — одобрение пользователя в браузере, и в этом весь смысл
потока.

## Типичный путь

```bash
ai-stp task start --intent account --idempotency-key account-session-01 --json
```

Следуйте `continuations`. Заблокированный вопрос authorization —
`actor=external`: покажите payload один раз и остановитесь.

Expert (незавершённый device code уже есть):

Сначала нужна идентичность устройства. Затем:

```text
ai-stp device init --json
ai-stp auth status --json
ai-stp auth login --provider github --json
```

`--provider` обязателен. Объявленные варианты — `github` и `google`.

Конверт login называет `user_code`, `verification_uri` и
`verification_uri_complete`. Откройте URI, одобрите код, затем:

```text
ai-stp auth complete --json
ai-stp auth status --json
```

`auth complete` не ждёт человека бесконечно. Если одобрения ещё не
было, команда отказывает, и вы спрашиваете снова. Машинный вызывающий
опрашивает сам. Не оборачивайте команду в цикл `sleep`, который
игнорирует `retryable`.

Чтобы позже закончить сессию, сохранив локальный реестр и паспорта:

```text
ai-stp auth logout --json
ai-stp auth status --json
```

Чтобы указать человеку на сайт для одного объекта каталога:

```bash
ai-stp link web --kind component --id <stable_id> --json
```

`--kind` и `--id` обязательны. `--kind` — `component`, `setup` или
`publisher`.

## Expert recovery: `auth login`

Начать вход и сообщить код, который пользователь должен одобрить.

```text
ai-stp auth login --provider github --json
```

Результат — первая половина ответа, а не сессия. Секрет здесь
непредставим. Device code, которым клиент опрашивает, лежит в
секретном хранилище, а не публикуется: это носитель незавершённой
авторизации.

Успешный `data` называет:

| Поле | Что это |
| --- | --- |
| `provider` | `github` или `google` |
| `user_code` | код, который человек вводит или подтверждает |
| `verification_uri` | страница одобрения |
| `verification_uri_complete` | та же страница с уже прикреплённым кодом |
| `expires_in` | сколько живёт эта незавершённая авторизация |
| `device_id` | устройство, которое будет держать сессию |
| `browser_opened` | открыли ли браузер на рабочем столе |
| `schema_version` | major схемы этого отчёта |

`next_actions` называет `auth complete` и `auth status`.

## Expert recovery: `auth complete`

Завершить ожидающий вход, когда пользователь его одобрил.

```text
ai-stp auth complete --json
```

При успехе результат — статус авторизации, а не ещё один объект
одобрения устройства. Локальные паспорта, которыми владел выпущенный
локальный аккаунт, переходят к аккаунту сервера ревизией.

Если человек отказал, код — `AI_STP_AUTHORIZATION_DECLINED`. Если
незавершённая авторизация истекла, код —
`AI_STP_AUTHORIZATION_EXPIRED`. Начните снова с `auth login`. Если
ничего не ожидает, код — `AI_STP_NOT_FOUND`.

## `auth logout`

Закончить облачную сессию на сервере и здесь, сохранив все локальные данные.

```text
ai-stp auth logout --json
```

Logout — не `device reset`. Идентичность устройства остаётся.
Кэшированные байты каталога остаются. Паспорта остаются. Сессия
заканчивается. После этого `auth status` сообщает `local_only`.

## `auth status`

Сообщить связь с платформой: только локально, authenticated, expired
или revoked.

```bash
ai-stp auth status --json
```

Это чтение. Оно не создаёт идентичность и сессию.

Успешный `data` называет:

| Поле | Что это |
| --- | --- |
| `state` | `local_only`, `authenticated`, `expired` или `revoked` |
| `account_id` | аккаунт, когда он есть, иначе `null` |
| `expires_at` | когда сессия истекает, или `null` |
| `credential_store` | где хранится секрет сессии, или `null` |
| `schema_version` | major схемы этого отчёта |

`local_only` — обычное состояние машины, которая никогда не входила.
Это не ошибка. Поиск в каталоге всё ещё работает. `device init` всё
ещё работает.

`expired` значит, что учётные данные были здесь и больше не действительны.
`revoked` значит, что аккаунт больше не доверяет этому устройству.
Ни то ни другое не чинится повтором `auth complete` без нового login.

## `link web`

Напечатать канонический веб-URL и обратимую ссылку CLI.

```bash
ai-stp link web --kind component --id <stable_id> --json
```

Это чтение. Оно не открывает браузер, не входит в аккаунт и не
загружает объект. Оно проецирует одну идентичность в URL сайта и в
команду CLI, которая называет тот же объект.

Успешный `data` называет:

| Поле | Что это |
| --- | --- |
| `web_url` | канонический URL сайта |
| `cli_command` | вызов CLI, который называет ту же цель |
| `cli_argv` | тот же вызов списком аргументов |
| `target` | `kind`, `stable_id` и необязательные `version`, `locale`, `intent` |

`--kind` — `component`, `setup` или `publisher`. `id` издателя —
`account_…`. Необязательные флаги версии, локали и действия жалобы
есть в machine help; они не обязательны, поэтому сюда не скопированы.

## Что содержит успешный конверт

`auth login` возвращает поля одобрения устройства выше. `auth complete`,
`auth logout` и `auth status` возвращают поля статуса авторизации выше.
`link web` возвращает поля deep-link выше.

Каждый конверт также несёт `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id` и `schema_version`.

## Чего эти команды никогда не делают

- не печатают refresh token, access token и незавершённый device code;
- не удаляют локальные паспорта, реестр и кэшированные байты при logout;
- не создают идентичность устройства (это `device init`);
- не ждут без границы, пока человек дойдёт до браузера;
- не пишут target harness;
- не считают URL сайта разрешением установить.

## Типичные отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` на `auth login` | нет `--provider` или это не `github`/`google` | `task start --intent account --idempotency-key account-session-01 --json` |
| `AI_STP_NOT_FOUND` на `auth complete` | ничего не ожидает | `task start --intent account --idempotency-key account-session-01 --json` |
| `AI_STP_AUTHORIZATION_DECLINED` | человек отказал в браузере | остановиться или снова стартовать `account`, если хотели одобрить |
| `AI_STP_AUTHORIZATION_EXPIRED` | незавершённый код истёк | `task start --intent account --idempotency-key account-session-01 --json` |
| `state` равен `expired` | сессия больше не действительна | `task start --intent account --idempotency-key account-session-01 --json` |
| `state` равен `revoked` | аккаунт больше не доверяет этому устройству | новый `account` start; `device reset` — отдельное destructive решение |
| `AI_STP_VALIDATION_ERROR` на `link web` | нет `--kind` или `--id`, или они неверны | передать обе обязательные опции |
| `AI_STP_AUTH_REQUIRED` на поздней облачной команде | сессии нет | `task start --intent account --idempotency-key account-session-01 --json` |

## Связанные страницы

| Страница | Зачем |
| --- | --- |
| [Устройство](device.md) | идентичность, которая держит сессию |
| [Паспорта](passport.md) | передача владения при первом входе |
| [Синхронизация](sync.md) | частный поток аккаунта после входа |
| [Вход на сайте](../web/login.md) | то же одобрение в браузере |
| [Аккаунт на сайте](../web/account.md) | аккаунт, которому принадлежит сессия |
| [Реестр](registry.md) | анонимное чтение каталога не требует входа |
| [Доступ](grant.md) | доступ к major-линии после входа |
| [Быстрый старт для человека](../quickstart/human.md) | что можно делать до аккаунта |

!!! note "Флаги из `ai-stp help --agent --json`"
    Если `help --agent` расходится с флагом на этой странице, прав CLI.
    Необязательные флаги здесь не перечислены. Читайте их из дескриптора.
    `auth login` требует `--provider`. `link web` требует `--kind` и
    `--id`.
