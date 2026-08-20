---
description: "Авторизованное чтение объектов владельца через CLI."
last_verified: "2026-08-13"
---

# Объекты владельца в CLI

`owner objects`, `owner object show` и `owner version show` являются только
читающей проекцией server-authorized owner models из `packages/contracts`.
Клиент не объединяет их с публичным каталогом, локальными паспортами или
полученными grants и не пытается самостоятельно определить владельца.

Список принимает необязательный закрытый фильтр вида объекта, bounded page size
и opaque cursor. Cursor только возвращается серверу; CLI не разбирает и не
пересобирает его. Detail адресует точный вид и устойчивый идентификатор, а
version detail дополнительно точную `X.Y`.

Состояния lifecycle, visibility, trust lane, независимые признаки
`author_verified` и `component_verified`, eligibility, evidence и возможность
начала публикации показываются ровно в серверной модели. Полученный grant не
создаёт owner object и не даёт команды записи в оригинал. Все три команды
требуют действующую cloud session и не передают локальные байты или credentials.
