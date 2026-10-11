"""Frozen functional taxonomy v2; IDs and existing seed identities never change.

Names are defaults, not a closed vocabulary. Tenant-owned edits and extensions
use the ordinary area/category registry. Russian labels are UI translations.
"""

from typing import Final

# Russian labels are explicitly localized user-facing strings.
# ruff: noqa: RUF001

TAXONOMY_PROVENANCE: Final = "ai_stp:technology-taxonomy:2"

# (English area, Russian area, ((code, English category, Russian category), ...))
_AREAS: Final = (
    (
        "Languages and runtimes",
        "Языки и среды выполнения",
        (
            ("languages", "Programming and query languages", "Языки программирования и запросов"),
            ("compilers", "Compilers", "Компиляторы"),
            ("interpreters", "Interpreters", "Интерпретаторы"),
            (
                "runtimes",
                "Language runtimes and virtual machines",
                "Языковые рантаймы и виртуальные машины",
            ),
        ),
    ),
    (
        "Client applications and interfaces",
        "Клиентские приложения и интерфейсы",
        (
            ("web-ui", "Web interfaces", "Веб-интерфейсы"),
            (
                "cross-platform-ui",
                "Cross-platform UI frameworks",
                "Кроссплатформенные UI-фреймворки",
            ),
            ("native-mobile", "Native mobile development", "Нативная мобильная разработка"),
            ("desktop-ui", "Desktop interfaces", "Настольные интерфейсы"),
            ("console-ui", "Console interfaces", "Консольные интерфейсы"),
            ("state-management", "State management", "Управление состоянием"),
            ("ui-components", "UI component systems", "Системы UI-компонентов"),
        ),
    ),
    (
        "Server applications",
        "Серверные приложения",
        (
            (
                "server-frameworks",
                "Server web and API frameworks",
                "Серверные веб- и API-фреймворки",
            ),
            ("application-servers", "Application servers", "Серверы приложений"),
            ("business-rules", "Business rule engines", "Движки бизнес-правил"),
            ("business-processes", "Business process engines", "Движки бизнес-процессов"),
            (
                "application-engines",
                "Specialized application engines",
                "Специализированные прикладные движки",
            ),
            ("validation", "Serialization and validation", "Сериализация и валидация"),
        ),
    ),
    (
        "Integration and messaging",
        "Интеграция и обмен сообщениями",
        (
            ("rpc", "RPC and interservice communication", "RPC и межсервисное взаимодействие"),
            ("api-contracts", "Protocols and API contracts", "Протоколы и API-контракты"),
            ("api-management", "API management", "Управление API"),
            (
                "connectors",
                "Integration platforms and connectors",
                "Интеграционные платформы и коннекторы",
            ),
            ("message-brokers", "Message brokers", "Брокеры сообщений"),
            ("event-streams", "Persistent event streams", "Сохраняемые потоки событий"),
            ("task-queues", "Task queues", "Очереди задач"),
            (
                "distributed-workflows",
                "Distributed workflow engines",
                "Движки распределённых workflow",
            ),
        ),
    ),
    (
        "Data storage and search",
        "Хранение и поиск данных",
        (
            ("relational-databases", "Relational databases", "Реляционные СУБД"),
            ("document-databases", "Document databases", "Документные СУБД"),
            ("key-value-databases", "Key-value databases", "Key-value-хранилища"),
            ("graph-databases", "Graph databases", "Графовые СУБД"),
            ("specialized-databases", "Specialized databases", "Специализированные СУБД"),
            ("analytical-databases", "Analytical databases", "Аналитические СУБД"),
            ("caches", "Caches", "Кэши"),
            ("search-engines", "Search engines", "Поисковые движки"),
            ("vector-engines", "Vector engines", "Векторные движки"),
            ("object-storage", "Object storage", "Объектное хранение"),
            ("file-storage", "File storage", "Файловое хранение"),
            ("block-storage", "Block storage", "Блочное хранение"),
            ("drivers-orm", "Database drivers and ORM", "Драйверы и ORM"),
            (
                "database-administration",
                "Database migrations and administration",
                "Миграции и администрирование БД",
            ),
        ),
    ),
    (
        "Data processing and analytics",
        "Обработка и аналитика данных",
        (
            ("data-ingestion", "Data ingestion and replication", "Загрузка и репликация данных"),
            (
                "data-transformation",
                "Data transformation and modeling",
                "Трансформация и моделирование",
            ),
            ("batch-processing", "Batch processing", "Пакетная обработка"),
            ("stream-processing", "Stream processing", "Потоковая обработка"),
            ("sql-engines", "SQL query engines", "SQL-движки запросов"),
            ("pipeline-orchestration", "Pipeline orchestration", "Оркестрация конвейеров"),
            ("bi", "BI and reporting", "BI и отчётность"),
            ("semantic-layers", "Semantic layers", "Семантические слои"),
            ("data-quality", "Data quality", "Качество данных"),
            ("data-catalogs", "Data catalogs and lineage", "Каталоги и происхождение данных"),
            ("analytics-formats", "Analytical storage formats", "Форматы аналитического хранения"),
        ),
    ),
    (
        "Artificial intelligence and ML",
        "Искусственный интеллект и ML",
        (
            ("ml-frameworks", "ML frameworks", "ML-фреймворки"),
            ("datasets", "Dataset preparation", "Подготовка датасетов"),
            ("model-training", "Model training", "Обучение"),
            (
                "model-registries",
                "Experiments and model registries",
                "Эксперименты и реестры моделей",
            ),
            ("models", "Models", "Модели"),
            ("inference", "Inference servers and APIs", "Серверы и API инференса"),
            ("agent-frameworks", "Agent frameworks", "Агентные фреймворки"),
            ("context-retrieval", "Context retrieval", "Поиск контекста"),
            (
                "model-evaluation",
                "Model evaluation and monitoring",
                "Оценка качества и мониторинг моделей",
            ),
        ),
    ),
    (
        "Compute and infrastructure",
        "Вычисления и инфраструктура",
        (
            ("operating-systems", "Operating systems", "Операционные системы"),
            ("virtualization", "Virtualization", "Виртуализация"),
            ("compute-platforms", "Compute platforms", "Вычислительные платформы"),
            ("container-runtimes", "Container runtimes", "Контейнерные рантаймы"),
            ("container-orchestration", "Container orchestration", "Оркестрация контейнеров"),
            ("serverless", "Serverless", "Serverless"),
            ("iac", "Infrastructure as Code", "Инфраструктура как код"),
            ("configuration-management", "Configuration management", "Конфигурационное управление"),
        ),
    ),
    (
        "Networks and traffic management",
        "Сети и управление трафиком",
        (
            ("dns", "DNS and service discovery", "DNS и обнаружение сервисов"),
            ("virtual-networks", "Virtual networks", "Виртуальные сети"),
            ("load-balancers", "Load balancers", "Балансировщики"),
            ("reverse-proxies", "Reverse proxies", "Обратные прокси"),
            ("forward-proxies", "Forward proxies", "Прямые прокси"),
            ("gateways", "Ingress and egress gateways", "Ingress- и egress-шлюзы"),
            ("service-mesh", "Service mesh", "Service mesh"),
            ("cdn", "CDN", "CDN"),
            ("vpn", "VPN and private connections", "VPN и частные соединения"),
        ),
    ),
    (
        "Security and access",
        "Безопасность и доступ",
        (
            ("authentication", "Authentication and SSO", "Аутентификация и SSO"),
            ("authorization", "Authorization", "Авторизация"),
            ("identity-management", "Identity management", "Управление идентичностями"),
            ("secrets", "Secrets and keys", "Секреты и ключи"),
            ("certificates", "Certificates", "Сертификаты"),
            ("security-analysis", "Security analysis", "Анализ безопасности"),
            ("runtime-protection", "Runtime protection", "Защита выполнения"),
            ("vulnerabilities", "Vulnerability management", "Управление уязвимостями"),
            ("security-audit", "Security audit", "Аудит безопасности"),
        ),
    ),
    (
        "Observability and reliability",
        "Наблюдаемость и надёжность",
        (
            ("metrics", "Metrics", "Метрики"),
            ("logs", "Logs", "Логи"),
            ("traces", "Tracing", "Трассировка"),
            ("profiling", "Profiling", "Профилирование"),
            ("error-monitoring", "Error monitoring", "Мониторинг ошибок"),
            ("telemetry", "Telemetry collection", "Сбор телеметрии"),
            ("incidents", "Alerts and incidents", "Оповещения и инциденты"),
            ("backup", "Backup", "Резервное копирование"),
            ("recovery", "Recovery", "Восстановление"),
            ("resilience-testing", "Resilience testing", "Проверки устойчивости"),
            (
                "resource-management",
                "Resource and cost management",
                "Управление ресурсами и затратами",
            ),
        ),
    ),
    (
        "Development, testing and delivery",
        "Разработка, тестирование и поставка",
        (
            ("source-control", "Source control", "Управление кодом"),
            ("ide", "IDEs", "IDE"),
            ("package-managers", "Package managers", "Менеджеры пакетов"),
            ("build", "Build tools", "Сборка"),
            ("artifact-registries", "Artifact registries", "Реестры артефактов"),
            ("ci-cd", "CI/CD", "CI/CD"),
            ("testing", "Testing", "Тестирование"),
            ("code-analysis", "Linters and type checking", "Линтеры и проверка типов"),
            ("deployment", "Deployment and GitOps", "Развёртывание и GitOps"),
            ("developer-portals", "Developer portals", "Порталы разработчиков"),
            ("documentation", "Documentation", "Документация"),
        ),
    ),
    (
        "Shared SaaS services",
        "Общие сервисы SaaS",
        (
            ("tenant-management", "Tenant management", "Управление клиентскими организациями"),
            ("plans", "Plans and features", "Тарифы и доступные функции"),
            ("billing", "Subscriptions, billing and payments", "Подписки, биллинг и платежи"),
            ("usage-accounting", "Usage accounting", "Учёт потребления"),
            ("quotas", "Quotas", "Квоты"),
            ("feature-flags", "Feature flags", "Feature flags"),
            ("notifications", "Notifications", "Уведомления"),
            ("content-media", "Content and media", "Контент и медиа"),
            ("localization", "Localization", "Локализация"),
            ("product-analytics", "Product analytics", "Продуктовая аналитика"),
        ),
    ),
)

TAXONOMY_AREAS: Final = tuple(
    (f"area_{index:026d}", name, localized)
    for index, (name, localized, _categories) in enumerate(_AREAS, 1)
)
TAXONOMY_CATEGORIES: Final = tuple(
    (f"category_{1000 + area * 100 + index:026d}", code, name, localized, f"area_{area:026d}")
    for area, (_name, _localized, categories) in enumerate(_AREAS, 1)
    for index, (code, name, localized) in enumerate(categories, 1)
)
CATEGORY_IDS: Final = {code: identifier for identifier, code, *_rest in TAXONOMY_CATEGORIES}

# Explicit functional classifications for every identity in technology-seed:1.
# Multiple classes describe product capabilities, never inferred project roles.
_TECHNOLOGY_GROUPS: Final = {
    "languages": tuple(range(8, 18)),
    "runtimes": (1, 18, 19, 254),
    "compilers": (225, 226),
    "package-managers": (1, 2, *range(20, 32)),
    "artifact-registries": (3, 144, 145),
    "ci-cd": (4, 5, *range(130, 137)),
    "web-ui": (6, *range(35, 41), 46, 47, 48, 68, 247),
    "cross-platform-ui": (49, 50, 54, 55),
    "desktop-ui": (44, 45),
    "console-ui": (248, 255, 256, 257),
    "state-management": (260, 261, 262, 263),
    "ui-components": (66, 67, 217, 264, 265),
    "server-frameworks": (32, 33, 34, 41, 42, 43, 51, 52, 239, 240, 241, 242, 243, 245, 246, 249),
    "application-servers": (159, 160, 292, 293),
    "validation": (65, 250),
    "rpc": (57, 69, 70, 258, 259),
    "api-contracts": (56, 58, 59),
    "api-management": (161,),
    "connectors": (53,),
    "message-brokers": (112, 113, 116, 117, 118, 119),
    "event-streams": (111, 114, 115),
    "task-queues": (120, 122, 289, 290, 291),
    "distributed-workflows": (121,),
    "relational-databases": (7, 83, 84, 90, 99, 100),
    "document-databases": (85, 94),
    "key-value-databases": (106, 108, 109),
    "graph-databases": (91, 101),
    "specialized-databases": (72, 89, 92, 93),
    "analytical-databases": (86, 95),
    "search-engines": (87, 88, 102, 103),
    "vector-engines": (71, 96, 97, 98),
    "object-storage": (104, 180),
    "drivers-orm": (60, 62, 63, 64, 270, 274),
    "database-administration": (61, 105),
    "caches": (107, 110),
    "pipeline-orchestration": (123, 124, 125),
    "batch-processing": (126, 128, 81, 267),
    "stream-processing": (127,),
    "data-transformation": (80, 129, 266),
    "bi": (268,),
    "agent-frameworks": (73,),
    "context-retrieval": (74,),
    "inference": (75, 76, 269),
    "ml-frameworks": (77, 78, 79, 82),
    "container-runtimes": (138,),
    "container-orchestration": (139, 140),
    "deployment": (141, 142, 143),
    "iac": (146, 147, 150),
    "configuration-management": (148, 251, 271),
    "virtualization": (151,),
    "serverless": (149, 190),
    "compute-platforms": (179, 181, 182, 183, 184, 185, 186, 187, 188, 189),
    "operating-systems": tuple(range(191, 200)),
    "reverse-proxies": (153, 154, 155, 156, 157, 158, 162),
    "load-balancers": (155, 156),
    "metrics": (163, 164, 173),
    "error-monitoring": (165,),
    "telemetry": (166, 167, 168, 170),
    "logs": (169, 272, 273),
    "traces": (171,),
    "incidents": (172,),
    "authentication": (174, 176, 177, 178, 253, 276, 277),
    "secrets": (175,),
    "security-analysis": (152,),
    "testing": (1, *range(200, 217), 279, 280, 281, 282, 283, 284, 285, 286, 287, 288),
    "build": (1, *range(218, 225), 237, 238, 294),
    "code-analysis": (137, *range(227, 237)),
    "billing": (275,),
    "content-media": (252,),
}
TAXONOMY_CLASSIFICATIONS: Final = {
    f"technology_{suffix:026d}": tuple(
        CATEGORY_IDS[code] for code, suffixes in _TECHNOLOGY_GROUPS.items() if suffix in suffixes
    )
    for suffix in {suffix for suffixes in _TECHNOLOGY_GROUPS.values() for suffix in suffixes}
}
