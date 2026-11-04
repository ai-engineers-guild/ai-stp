# ai-stp

[English](README.md) · [Каталог](https://ai-stp.aiguild.space) ·
[Документация](https://docs.nddev.asia/)

ai-stp — CLI на Rust для создания и установки конфигураций ИИ-харнессов.
Сетап закрепляет неизменяемые версии компонентов для одного харнесса. Веб
предоставляет аккаунт и публичный каталог. CLI и Desktop используют один движок.

## Начало работы

Скачайте и проверьте архив или установите CLI через пакетный менеджер по
[руководству установки](apps/cli/README.md#install-and-update).
Для нового локального состояния:

```sh
ai-stp init --credential-store os_keyring --json
ai-stp help --agent --json
```

Состояние старого Python CLI переносится по
[отдельной процедуре](apps/cli/README.md#state-and-first-run).
Локальная работа не требует аккаунта или ключа модели.

Нативная настройка и передача активной сессии проверяются на Linux x86-64,
macOS Apple Silicon и Windows x86-64. Проверьте `native_configuration` в
`ai-stp capabilities --json` на своей системе. Сам харнесс устанавливает и
обновляет пользователь или поставщик.

[Desktop](apps/desktop/README.md) · [Разработка](CONTRIBUTING.md) ·
[Безопасность](SECURITY.md)

[AGPL-3.0-or-later](LICENSE). Опубликованные конфигурации сохраняют свои лицензии.
