# Catalog

Намерения: найти skill или сетап, показать версию, забрать байты.

Берите из machine help: `ai-stp registry search`, `ai-stp registry show`,
`ai-stp registry version`, `ai-stp registry fetch`, `ai-stp registry acquire`.

Закрепляйте точный `id` и `X.Y`. По умолчанию линия `authoritative`.
`experimental` — только с явным consent, в отдельном разделе. Ключ объекта не
даёт права скачивать. Проверьте возвращённую идентичность до compose или
install.

Приватные версии требуют явного authenticated-доступа владельца или по гранту
из дескриптора. Публичный поиск остаётся анонимным. Отказ онлайн остаётся
отказом; ранее полученные локальные копии доступны через явный offline-путь.
Приватный доступ не подтверждает author_verified или component_verified.
