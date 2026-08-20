---
description: "Версионированные agent-first deep links между CLI и web без сетевого поиска и скрытого запуска браузера."
last_verified: "2026-08-09"
---

# ADR-0064: Канонические CLI/web deep links

Статус: принято.

## Контекст

CLI и web уже называют одни stable IDs и exact versions, но переходы между ними
не имеют общего контракта. Простая конкатенация строк в каждом consumer создаст
разные plural routes, локали, quoting и report URLs. Команда `open`, в свою очередь,
непригодна как основной agent contract: по SSH browser отсутствует, а скрытый launch
является side effect у команды, которая должна только ориентировать агента.

Маршруты component/setup exact version и publisher уже существуют в web. Маршрут
создания report принадлежит будущей platform/web работе и ещё не заморожен; CLI не
должен изобретать его за владельца платформы.

## Решение

Принимается grammar `deep_link_v1` и pure CLI command, которая печатает
`DeepLinkView`: нормализованный target, абсолютный canonical URL, структурированный
`cli_argv` и его детерминированную human projection. Browser автоматически не
открывается.

Component/setup object и exact version используют существующую route hierarchy.
Publisher использует public profile route по `account_` stable ID. Report intent
адресует exact version и добавляет единственный разрешённый fragment `#report`.
Так intent можно сохранить до появления UI действия, не создавая API/server route и
не меняя правила non-enumeration.

Default locale — `ru`, как в web routing. Обе канонические локали всегда присутствуют
в URL явно. Platform base берётся из действующей конфигурации и проходит существующую
проверку scheme/authority; deep-link parser дополнительно требует exact configured
origin и base path.

Grammar реализуется в shared contracts package и сопровождается одним packaged JSON
corpus. CLI использует Python implementation; web owner реализует route/parser и
проверяет его тем же corpus. Генерация не делает lookup: иначе команда одновременно
стала бы сеть-зависимой, offline-непригодной и oracle существования private target.

## Рассмотренные варианты

1. Автоматически открывать browser. Отвергнуто как недетерминированный side effect,
   который не работает одинаково локально и по SSH.
2. Добавлять URL в ответы каждой catalog command. Отложено: это дублирует grammar во
   многих моделях и не покрывает publisher/report единым действием.
3. Создать `/reports/new` из CLI. Отвергнуто: route и authorization принадлежат
   platform/web owner и ещё не заморожены.
4. Использовать query string для идентичности. Отвергнуто: существующие ресурсные
   маршруты уже выражают идентичность в пути, а query проще случайно расширить
   данными сессии.

## Последствия

Агент получает точный URL и безопасный `argv` без shell quoting и без сети. Web может
показывать копируемую команду, не поддерживая второй словарь routes. Наличие ссылки не
утверждает наличие или доступность объекта; окончательный ответ остаётся за web/API.
Report intent требует anchor с именем `report` на exact-version surface, когда
platform/web slice будет реализован.

## Условия пересмотра

Решение пересматривается при появлении третьей локали, отдельного неизменяемого
report target, сервиса коротких ссылок или несовместимой иерархии маршрутов. Каждое
такое изменение получает новую версию грамматики, а не меняет `deep_link_v1` по месту.
