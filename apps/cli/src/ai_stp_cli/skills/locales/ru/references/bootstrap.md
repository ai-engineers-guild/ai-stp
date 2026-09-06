# Bootstrap

Намерения: первое сообщение после установки, «установлен ли ai-stp», version,
«настрой меня», какие проекты индексировать.

Берите из machine help: `ai-stp doctor`, `ai-stp help`, `ai-stp capabilities`,
`ai-stp version`, `ai-stp skill install`, `ai-stp project discover`,
`ai-stp project index`, `ai-stp component inventory`, `ai-stp component adopt`.

Запустите `ai-stp doctor --json`, затем `ai-stp help --agent --json`. Картина —
конверт `ok` и состояние установки. Вызывайте только команды, которые вернул
help. Не изобретайте отсутствующую команду.

После этих двух чтений, если это первый запуск или пользователь просил
настроить:

1. Спросите, какие директории проектов индексировать. Это называет их деревья;
   это не remaining stop из `decisions.md`.
2. Для каждого названного корня возьмите из machine help `project discover` и
   `project index`. Частичный индекс остаётся частичным; не называйте его
   полным.
3. Возьмите `component inventory` на тех же корнях. Каждый найденный компонент
   регистрируйте через `component adopt`. Повторный adopt того же источника —
   no-op.
4. Если doctor показывает, что этот Skill не установлен в харнессе, которым
   они пользуются, возьмите `skill install` из machine help.

Не сканируйте домашний каталог. Не изобретайте корни. Не пишите harness target.
