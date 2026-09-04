# Daily

Намерения: есть ли drift, выбранное vs установленное.

Берите из machine help: `ai-stp target status`, `ai-stp target diff`,
`ai-stp install status`.

Различайте `local_drift`, `catalog_drift` и `pending_install`. Ни один drift не
разрешается сам. `local_drift` предлагает restore или новую версию.
`catalog_drift` предлагает обновление после нового плана. Ожидание установки
выбранной версии — не drift.
