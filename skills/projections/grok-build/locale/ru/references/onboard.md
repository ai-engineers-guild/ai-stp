# Onboard

Намерения: настроить локально, developer passport, device passport.

Первая обнаружимость харнесса — intent `initialize`, не config init.
Если пользователь спросил, что сломано, стартуйте `inspect`. Не запускайте
`ai-stp doctor` или `ai-stp config show` как прелюдию к каждой мутации.

Config, device identity и developer passport остаются экспертными. Не набирайте
`ai-stp config init`. Стартуйте intent `initialize`. Берите из machine help:
`ai-stp config show`, `ai-stp config set`, `ai-stp config validate`,
`ai-stp passport developer init`,
`ai-stp passport developer show`, `ai-stp device init`, `ai-stp device show`,
`ai-stp passport device show`, `ai-stp passport device refresh`. Не кладите
секреты в config.

Отсутствие config-файла допустимо при полных defaults. На новой установке
registry и device identity могут ещё не существовать: их создаёт нужная команда
инициализации. Сохраняйте наблюдаемые факты и уже принятые решения, не
выдумывайте персональные сведения ради зелёного статуса.

`initialize` пишет только через связанный провайдер. Если задача блокируется
с `question_id` `provider-too-old`, сообщите это ограничение и остановитесь.
Не стартуйте `account`. Не крутите `task continue`. Не набирайте
`provider network`. Байты не пишутся, пока провайдер не объявит операцию.
