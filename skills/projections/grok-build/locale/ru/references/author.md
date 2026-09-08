# Author

Намерения: scaffold skill, adopt дерева, опубликовать компонент или сетап.

Берите из machine help: `ai-stp component scaffold plan`,
`ai-stp component scaffold apply`, `ai-stp component template render`,
`ai-stp component source parse`, `ai-stp component adopt`,
`ai-stp component passport validate`, `ai-stp component skill validate`,
`ai-stp component version release`, `ai-stp component publish`,
`ai-stp publication plan`, `ai-stp publication confirm`,
`ai-stp setup publish plan`, `ai-stp attestation sign`.

Замените каждый маркер черновика scaffold до compose или release. Запускайте
`ai-stp component skill validate` на каталоге пакета (каталог с `SKILL.md` в
корне), не на всём авторском дереве. Публичность и доступ — отдельное решение.

Новые версии и отправка по умолчанию приватны. Приглашайте получателей через
grant-команды из machine help. Для открытия существующей версии берите
`ai-stp publication visibility plan`, `ai-stp publication visibility status` и
`ai-stp publication visibility confirm`; получите явное решение владельца по
проверенному эффекту доступа. Версия и digest паспорта сохраняются. Отсутствие
поддержки на сервере — недоступная зависимость, а не разрешение использовать
публичную публикацию как запасной путь.

`setup compose` создаёт приватный локальный сетап и разрешает точные предоставленные
pins через аутентифицированное чтение после отсутствия версии в публичном каталоге.
Проверьте digest плана перед apply; публичное открытие остаётся отдельным решением.

Portable scaffold хранит редактируемые нативные файлы в `source/`. Прочитайте
результат scaffold перед выбором корня adopt. Выпущенная версия неизменяема:
публикуйте сохранённый артефакт через publication plan/confirm, не пересобирая
его из изменённого каталога. Новые правки требуют новой версии до публикации.
