# Compose

Чтобы добавить или убрать член сохранённого сетапа, стартуйте intent `change`.
Не набирайте `ai-stp setup compose plan`, `ai-stp setup compose apply` или
`ai-stp setup update apply`. Движок выпускает новый identity сетапа, записывает
линейку к источнику и устанавливает производный pin. Исходный setup id остаётся
восстановимым.

1. Передайте `harness_id`, исходные `setup_id`/`setup_version` если известны, и
   `component_id`/`component_version`. Без источника движок берёт first-party
   `baseline` этого харнесса. Без action это `add`.
2. Вызовите `ai-stp task start` с intent `change` и исполняйте continuation
   `argv` только когда `actor` — `cli`. Один blocked вопрос — через `ai-stp task answer`.
3. Сообщите derived setup id, был ли выпущен новый identity, и native
   verification. Одного `ok` в конверте недостаточно.

Состав, который не является одной дельтой члена, всё равно `install`, когда
identity сетапа уже есть. Не набирайте `select propose`, `select confirm`,
`select bundle` или compose plan/apply. Не набирайте `setup recast plan` или
`setup recast apply`. Recast, materialize и portability
остаются в machine help; не хореографируйте их plan/apply из этого playbook.

Готовый опубликованный сетап ставьте через [install](install.md), не собирайте
его по компонентам.
