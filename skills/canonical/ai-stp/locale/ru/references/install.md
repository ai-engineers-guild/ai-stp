# Установка, сохранение и возврат

Для готового сетапа каталога стартуйте intent `install`. Не набирайте
группу install без leaf, и не набирайте `ai-stp install plan`,
`ai-stp install approve` или `ai-stp install apply`.
Движок задачи сливает их in-process.

1. Возьмите харнесс и абсолютный корень проекта из разговора.
   Если пользователь назвал точный сетап, передайте `setup_id` и `setup_version`.
   Иначе движок выбирает один first-party pin `baseline` для этого харнесса.
   Каталог он квизовать не будет. Отсутствующий project, developer или
   device passport он минтит in-process. Не набирайте `project passport`.
   Типизированный отказ изоляции приходит с пустым `continuations` и
   `error.details.state=failed`. Остановитесь. Не набирайте `provider network`.
   Не выдумывайте `task get`.
2. Вызовите `ai-stp task start` с intent `install` и исполняйте continuation
   `argv` только когда `actor` — `cli`. Один blocked-вопрос передайте через
   `ai-stp task answer`.
3. В отчёте — проверка payload: идентичность сетапа, operation id и то, что
   нативное состояние `verified`. Одного `ok` конверта недостаточно.
   `pending_authorization` — незавершённый вход, а не повод повторить apply.

Чтобы вернуть последнюю рабочую пользовательскую конфигурацию, стартуйте
intent `switch`. Не набирайте `ai-stp setup restore plan` или
`ai-stp setup preserve plan`. Движок восстанавливает новейший пользовательский
`preserved_setup` для этого target, никогда не pin каталога. Сначала он
сохраняет текущий drift как leftover.

1. Передайте `harness_id` и абсолютный `project_root`, если они известны.
   Явный `preserved_setup_id` выбирает этот снимок; иначе берётся новейшая
   сохранённая пользовательская конфигурация target. Отсутствующий снимок —
   `not found`, не квиз каталога. Не отвечайте на `project-root` каталогом
   конфигурации харнесса.
2. Вызовите `ai-stp task start` с intent `switch` и исполняйте continuation
   `argv` только когда `actor` — `cli`. Вопрос `reload-session` передайте через
   `ai-stp task answer` после того, как человек перезагрузит сессию харнесса.
   Не убивайте вызывающий процесс.
3. В отчёте — восстановленная идентичность, leftover id, operation id и то,
   что `session_loaded` равно false. Файлы уже могут быть записаны, пока задача
   ещё `blocked`. Одного `ok` конверта недостаточно.

Публичное получение не требует входа. Если отсутствует сама программа харнесса,
следуйте [provider](provider.md). Prefix программы отделён от target
конфигурации.

После прерывания сначала откройте [recover](recover.md). Expert recovery по
запросу всё ещё использует `ai-stp install recover` и `ai-stp install status`;
не дампьте весь реестр.

Сохранённую идентичность ищите в machine help. Offline-запись не является
свежим измерением. Существующая native-конфигурация как редактируемый
локальный сетап — экспертный import, не точка восстановления; не набирайте
`setup restore plan`.
