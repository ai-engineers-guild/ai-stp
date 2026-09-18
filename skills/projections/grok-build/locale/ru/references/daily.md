# Daily

Намерения: есть ли drift, выбранное vs установленное.

Когда пользователь спрашивает про drift, стартуйте intent `inspect`. Не
дампьте `ai-stp target status` как прелюдию к каждой сессии.

Различайте `local_drift`, `catalog_drift` и `pending_install`. Ни один drift не
разрешается сам. `local_drift` предлагает intent `switch` для последней
рабочей пользовательской конфигурации или новую версию. `catalog_drift`
предлагает обновление после нового плана. Ожидание установки выбранной версии —
не drift.

Дальнейшая диагностика: из machine help `ai-stp target status`,
`ai-stp target diff` и `ai-stp install status`.
