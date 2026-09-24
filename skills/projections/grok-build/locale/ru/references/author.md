# Author

Чтобы зарегистрировать локальный каталог как компонент, стартуйте intent
`author`. Не набирайте `ai-stp component adopt`, `ai-stp component scaffold plan`,
`ai-stp component scaffold apply`, `ai-stp setup compose apply` или
`component materialize plan`.
Движок замораживает каталог как один встроенный компонент и один новый
identity сетапа. Он не устанавливает сетап и не мутирует сохранённый сетап
на месте.

1. Передайте `directory`, `harness_id`, `component_type`, `name` и
   `license_spdx`, если известны. Виды берутся из `COMPONENT_TYPES`,
   отфильтрованных native-поверхностями харнесса. Пропущенные поля — один
   типизированный вопрос каждый.
2. Вызовите `ai-stp task start` с intent `author` и исполняйте continuation
   `argv` только когда `actor` — `cli`. Один blocked вопрос — через `ai-stp task answer`.
3. Сообщите component id, новый setup id и был ли выпущен новый identity.
   Одного `ok` в конверте недостаточно. Установка этого pin — intent
   `install`, когда пользователь хочет его на цели.

Scaffold, adopt, validate и release остаются экспертными: их семейства —
в machine help, не набирайте их plan/apply. Публичность — отдельное решение;
после `author` стартуйте intent `publish`. Не набирайте
`ai-stp publication plan`, `ai-stp publication confirm`,
`setup publish plan` или `setup publish confirm`. Происхождение —
локальная файловая система; не выдумывайте git-историю. Не набирайте
remote `github.com`. Новые публикации по
умолчанию private. Квитанция worker не означает читаемый результат каталога,
пока `readable` в outcome не true.

Publish принимает `object_id` компонента или сетапа с точным `object_version`.
Публикация сетапа сохраняет весь граф в `outcome.publication_set`; следуйте
continuation той же задачи для подтверждения именно этого набора. Сохраняйте
частичные результаты участников и не заявляйте читаемость раньше времени.
`provider` — провайдер входа (`google` или `github`), а не метка filesystem.

Участник набора публикации сохраняет серверные `evidence`: причины проверок и
ограниченные сводки. Прочитай их перед повторной попыткой; `goal_satisfied=false`
не означает публикацию. Неизменяемый паспорт локального владельца не
переписывается после входа. Встроенные компоненты остаются встроенными в новом
производном setup; change не превращает их в публикации каталога.
