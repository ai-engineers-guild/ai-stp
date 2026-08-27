---
description: "Машиночитаемые границы CLI, API, синхронизации, паспортов и провайдеров."
last_verified: "2026-08-03"
---

# Контракты

<!-- СОДЕРЖИМОЕ: генерируется через just docs-gen, руками не править -->

| Документ | О чём | Сверено |
| -------- | ----- | ------- |
| [access-grants-and-forks.md](access-grants-and-forks.md) | Цель права доступа, действия получателя, форк, производная публикация и последствия отзыва. | 2026-08-04 |
| [canonical-data.md](canonical-data.md) | Канонические идентификаторы, сериализация, ссылки, хэши и подписи. | 2026-08-05 |
| [capability-vocabulary.md](capability-vocabulary.md) | Закрытый словарь требуемых возможностей, правило его роста и разница между неизвестной и отсутствующей возможностью. | 2026-08-08 |
| [catalog-reactions.md](catalog-reactions.md) | Приватные reactions аккаунта на публичные компоненты и сетапы каталога. | 2026-08-17 |
| [catalog-support-evidence.md](catalog-support-evidence.md) | Безопасная публичная проекция evidence поддержки харнесса в каталоге. | 2026-08-09 |
| [catalog-usage-metrics.md](catalog-usage-metrics.md) | Проводная семантика публичных detail view и artifact download counters. | 2026-08-17 |
| [cli-config.md](cli-config.md) | Поля глобального конфига CLI, значения по умолчанию и приоритет источников. | 2026-08-04 |
| [cli-copy-templates.md](cli-copy-templates.md) | Канонические CLI-шаблоны для copy-блоков веб-UI (SPEC-037). | 2026-08-13 |
| [cli-grants.md](cli-grants.md) | Клиентская последовательность выдачи, принятия и отзыва прав доступа. | 2026-08-13 |
| [cli-json.md](cli-json.md) | Конверт JSON, классы ошибок и правила машинного вывода CLI. | 2026-08-13 |
| [cli-owner-objects.md](cli-owner-objects.md) | Авторизованное чтение объектов владельца через CLI. | 2026-08-13 |
| [cli-publication.md](cli-publication.md) | Клиентская последовательность publication plan и граница передаваемых данных. | 2026-08-25 |
| [cli-telemetry.md](cli-telemetry.md) | Закрытый перечень полей анонимного пинга телеметрии, условия отправки и то, что в него не попадает. | 2026-08-21 |
| [complaint-intake.md](complaint-intake.md) | Публичный приём обращений: поля, отличие от закрытого report case и конфигурируемые лимиты. | 2026-08-22 |
| [component-authoring-templates.md](component-authoring-templates.md) | Версионируемые scaffold-планы и безопасная проекция authoring templates компонентов. | 2026-08-13 |
| [component-presentation.md](component-presentation.md) | Изменяемое представление компонента в каталоге без изменения паспорта версии. | 2026-08-10 |
| [component-setup-passports.md](component-setup-passports.md) | Паспорта версий компонентов и сетапов, виды компонентов и зависимости. | 2026-08-22 |
| [composition-reports.md](composition-reports.md) | Отчёты состава и преобразования: закрытый перечень классов конфликтов, разрешённые операции сборщика и состояния потерь. | 2026-08-08 |
| [deep-links.md](deep-links.md) | Грамматика канонических URL и CLI references для component, setup, publisher и report intent. | 2026-08-15 |
| [device-passport.md](device-passport.md) | Поля паспорта устройства, его приватность и разрешённая сводка для сервера и веба. | 2026-08-04 |
| [eligibility-constraints.md](eligibility-constraints.md) | Механические ограничения до выбора агентом: закрытый перечень причин отказа, порядок проверок и две независимые оси допустимости. | 2026-08-26 |
| [federated-sources.md](federated-sources.md) | Машинный контракт общих descriptors для local ports и metadata adapters. | 2026-08-16 |
| [fixture-corpus.md](fixture-corpus.md) | Общий корпус фикстур /v1: виды случаев, инварианты и порядок использования обеими сторонами. | 2026-08-05 |
| [github-archive-evidence.md](github-archive-evidence.md) | Машинный контракт локального GitHub archive evidence и истории наблюдений. | 2026-08-15 |
| [harness-bundle.md](harness-bundle.md) | Ограниченный и детерминированный пакет для публичного провайдера харнесса. | 2026-08-09 |
| [http-api.md](http-api.md) | Версионирование HTTP API, полномочия, идемпотентность и конкуренция. | 2026-08-25 |
| [native-component-discovery.md](native-component-discovery.md) | Машинный контракт read-only обнаружения нативных компонентов поддерживаемых харнессов. | 2026-08-26 |
| [offline-capability.md](offline-capability.md) | Что работает без сети после первичной настройки и что требует подключения. | 2026-08-13 |
| [operation.md](operation.md) | Состояния, план, журнал и восстановление изменяющей операции. | 2026-08-09 |
| [passport-envelope.md](passport-envelope.md) | Канонический конверт паспорта и происхождение фактов. | 2026-08-04 |
| [project-discovery.md](project-discovery.md) | Машинная форма полного discovery проектов в явно названной области. | 2026-08-09 |
| [provider-protocol.md](provider-protocol.md) | Команды, граница исполнения и соответствие состояний публичного провайдера. | 2026-08-27 |
| [provider-release.md](provider-release.md) | Манифест, доверие, проверка и защита от отката выпуска провайдера. | 2026-08-25 |
| [public-profile.md](public-profile.md) | Поля публичного профиля, ревизии, avatar и отделение от паспорта разработчика. | 2026-08-08 |
| [report-case.md](report-case.md) | Закрытый случай жалобы: разрешённый состав, предпросмотр, состояния и аудируемые действия модератора. | 2026-08-13 |
| [selection-impact.md](selection-impact.md) | Машинный контракт локального бюджета контекста, capability delta и blast radius. | 2026-08-15 |
| [selection-proposal.md](selection-proposal.md) | Недолговечное предложение состава, его подтверждение и атомарная фиксация SetupVersion. | 2026-08-09 |
| [setup-evaluation.md](setup-evaluation.md) | Машинный контракт профиля, плана и результата локальной оценки точного SetupVersion. | 2026-08-13 |
| [setup-graph.md](setup-graph.md) | Точное замыкание зависимостей сетапа: узел, детерминированный порядок, закрытый перечень отказов и пределы ресурсов. | 2026-08-08 |
| [setup-import.md](setup-import.md) | Машинная граница обнаружения и регистрации существующего нативного сетапа. | 2026-08-12 |
| [setup-store-ports.md](setup-store-ports.md) | Контракт локального обнаружения, preview и импорта компонентов из SX и APM. | 2026-08-13 |
| [sync-event.md](sync-event.md) | Поля, ответы, повтор и конфликты события синхронизации. | 2026-08-15 |
| [tag-vocabulary.md](tag-vocabulary.md) | Формат словаря тегов, нормализация, предел и поведение поиска. | 2026-08-04 |
| [unverified-consent.md](unverified-consent.md) | Сеансовый признак согласия на непроверенное и долговечные записи исключений по издателю и основной линии. | 2026-08-04 |
| [validation-policy.md](validation-policy.md) | Обязательные проверки по видам компонентов, классам MCP и сетапу. | 2026-08-23 |
| [web-cookie-consent.md](web-cookie-consent.md) | Категории cookies и правило запуска необязательных интеграций Web. | 2026-08-22 |
| [web-machine-projection.md](web-machine-projection.md) | Поля машинного документа web, парные URL и запрет утечек. | 2026-08-16 |

<!-- КОНЕЦ СОДЕРЖИМОГО -->
