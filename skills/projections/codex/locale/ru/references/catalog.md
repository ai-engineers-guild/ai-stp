# Catalog

Намерения: найти skill или сетап, показать версию, забрать байты.

Не набирайте `registry search` или `registry acquire`. Не набирайте
`registry port discover`, `registry port inspect`, `registry port plan` или
`registry port import`. Не набирайте `registry show`, `registry fetch` или
`registry version` для обычного setup. Байты каталога для
обычного install идут через intent `install`. Identity inspect остаётся
expert machine help, когда пользователь спросил, что это за объект, а не
как его ставить.

Закрепляйте точный `id` и `X.Y`. По умолчанию линия `authoritative`.
`experimental` допустим в рамках уже разрешённой задачи, с явной маркировкой
в отдельном разделе. Ключ объекта не даёт права скачивать. Проверьте
возвращённую идентичность до install.

Приватные версии требуют явного authenticated-доступа владельца или по гранту
из дескриптора. Публичный поиск остаётся анонимным. Отказ онлайн остаётся
отказом; ранее полученные локальные копии доступны через явный offline-путь.
Приватный доступ не подтверждает author_verified или component_verified.
