# Onboard

Намерения: настроить локально, developer passport, device passport.

Берите из machine help: `ai-stp config init`, `ai-stp config show`,
`ai-stp config set`, `ai-stp config validate`, `ai-stp passport developer init`,
`ai-stp passport developer show`, `ai-stp device init`, `ai-stp device show`,
`ai-stp passport device show`.

Перед мутацией прочитайте `ai-stp doctor` и `ai-stp config show`. Не кладите
секреты в config. Проверяйте `ai-stp doctor` и соответствующей командой `show`.

Отсутствие config-файла допустимо при полных defaults. На новой установке
registry и device identity могут ещё не существовать: их создаёт нужная команда
инициализации. Когда композиции нужны паспорта, инициализируйте developer и
выполните `ai-stp passport device refresh`, затем соответствующие show-команды.
Сохраняйте наблюдаемые факты и уже принятые решения, не выдумывайте персональные
сведения ради зелёного статуса.
