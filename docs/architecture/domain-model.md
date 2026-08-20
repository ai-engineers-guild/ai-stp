---
description: "Сущности продукта, их владение и основные инварианты."
last_verified: "2026-08-08"
---

# Доменная модель

## Identity и устройства

| Сущность | Смысл |
|---|---|
| Account | Внутренний пользователь платформы. |
| OAuthIdentity | Связанный Google или GitHub identity. |
| PublicProfile | Отдельно заполняемый публичный объект, не проекция паспорта. |
| Device | Установка CLI с отдельным ID и ключом. |
| AccessGrant | Право account ID получить приватный объект или major-линию. |
| GrantInvitation | Приглашение на подтверждённую почту до появления права. |
| AuditEvent | Неизменяемая запись чувствительного действия. |
| ReportCase | Закрытый случай жалобы с механическими доказательствами и аудируемой модерацией. |

## Паспорта и проекты

| Сущность | Смысл |
|---|---|
| DeveloperPassport | Частный межустройственный профиль предпочтений и истории решений. |
| DeveloperPassportRevision | Неизменяемая ревизия паспорта. |
| DevicePassport | Частный паспорт окружения одного устройства: OS, architecture, харнессы и инструменты. |
| DevicePassportRevision | Неизменяемая ревизия паспорта устройства. |
| Project | Зарегистрированный локальный проект. |
| ProjectPassport | Структурированные факты и требования проекта. |
| ProjectIndex | Индекс ограниченных безопасных файлов и символов. |
| Fact | Значение с происхождением, подтверждением и ссылками на источник. |

## Registry

| Сущность | Смысл |
|---|---|
| Component | Стабильная логическая сущность компонента с закрытым `component_type` из восьми значений. |
| ComponentVariant | Нативная реализация компонента для одного харнесса. |
| ComponentVersion | Неизменяемая версия `X.Y`. |
| Setup | Стабильная логическая сущность сетапа, принадлежащая одному харнессу. |
| SetupVersion | Неизменяемая версия сетапа. |
| SetupLineage | Необязательная связь происхождения между сетапами разных харнессов. |
| DraftRevision | Изменяемая private history до freeze/publish. |
| Artifact | Content-addressed bytes с точным хэшем. |
| ValidationSnapshot | Результаты проверок exact digest. |
| EvidenceBinding | Принятый источник доказательства одной обязательной проверки со сроком. |
| PublicationPlan | Неизменяемый серверный план публикации (Operation) с plan_hash. |

## Сборка

| Сущность | Смысл |
|---|---|
| SelectionRun | Контекст, вопросы, candidates и решения. |
| SelectionProposal | Производное недолговечное предложение состава внутри сеанса рекомендации. |
| UnverifiedConsent | Долговечная запись согласия области publisher или object_major с отпечатком полномочий. |
| RecommendationTrace | Линия доверия, источник согласия и причины выбора кандидата. |
| SetupGraph | Узлы компонентов и зависимости. |
| Overlay | Ограниченное изменение поверх upstream version. |
| Conflict | Неразрешённое противоречие. |
| CompositionReport | Почему выбран каждый компонент. |
| ConversionReport | Полнота нативной адаптации. |
| HarnessBundle | Проверенный пакет для provider. |

## Установка

| Сущность | Смысл |
|---|---|
| ProviderRelease | Exact version публичного setup-manager. |
| HarnessTarget | Изолированный каталог runtime/configuration. |
| ImportedSetup | Личный сетап, созданный из существующей нативной конфигурации. |
| InstallPlan | Side-effect-free план с digest и предусловиями. |
| Operation | Durable plan/apply/verify lifecycle. |
| InstallationSnapshot | Состояние до и после операции. |
| BackupRef | Ссылка на provider-owned backup. |
| ActiveTargetPointer | Выбранный target следующего запуска. |

## Синхронизация

| Сущность | Смысл |
|---|---|
| EntityRevision | Content-addressed revision с parents. |
| DeviceHead | Последняя известная ревизия сущности на устройстве. |
| ServerHead | Текущая принятая сервером ревизия сущности в одном account. |
| SyncCursor | Позиция принятого server stream. |
| LocalOutboxEvent | Локальное изменение, ожидающее отправки. |
| ServerOutboxEvent | Упорядоченная запись о принятом сервером изменении для pull. |
| SyncReceipt | Долговечный идемпотентный результат одного server sync event. |
| Tombstone | Явное удаление. |
| ConflictRecord | Неразрешённое параллельное изменение. |

## Владение данными

| Данные | Владелец |
|---|---|
| Файлы target | локальный провайдер харнесса |
| Installation state | устройство |
| Local draft | локальный реестр, облачная копия опциональна |
| Published metadata и version | сервер |
| Visibility, grants, verified badge | сервер |
| Project index | устройство; облако только после opt-in |
| Backup bytes | провайдер на устройстве |
| Создание паспортов и установка | CLI и агент пользователя |
| Аккаунт, приватность, устройства и публикация | общий сценарий для web и CLI |

## Инварианты

- DeveloperPassport private по умолчанию.
- Наблюдаемые факты окружения принадлежат DevicePassport; DeveloperPassport их не содержит.
- Паспорта устройств не объединяются между устройствами; межустройственно объединяется только DeveloperPassport.
- PublicProfile заполняется отдельно и не получает поля из паспорта автоматически.
- Факт хранит происхождение и подтверждение как две независимые оси.
- Published version immutable.
- Version `X.Y` не переиспользуется для другого digest.
- Setup принадлежит одному `harness_id`, заданному при создании.
- Идентичность SetupVersion не содержит вариант; родство сетапов выражается SetupLineage.
- SetupVersion pin'ит exact ComponentVersion.
- SelectionProposal недолговечно; SetupVersion возникает только из явного подтверждения пользователя.
- Зависимости компонента разделены на `requires_components` и `requires_capabilities`.
- Major-линия определяет будущую access boundary.
- Получатель права читает, устанавливает и форкает, но не редактирует оригинал.
- Неизменённый клон не переиздаётся; производная публикация требует содержательного изменения.
- InstallationSnapshot не дублирует backup bytes.
- BackupRef и ImportedSetup остаются разными объектами.
- Device signature не равна platform-executed validation.
- Unverified object входит в выдачу только по явному согласию и не попадает в authoritative lane.
- Запись согласия ограничена областью publisher или object_major и отменяется расширением полномочий.
- `author_verified` и `component_verified` являются независимыми осями.
- AccessGrant не создаётся знанием account ID или адреса почты.
- Число жалоб само не меняет жизненный цикл версии; скрытие и блокировка — аудируемые действия модератора.
- Пригодность к установке выводится из актуальных обязательных доказательств и не отключает установленные цели.
- Published version не merge'ится; выпускается новая версия.
