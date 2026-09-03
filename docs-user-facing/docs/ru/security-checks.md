---
title: Проверки безопасности
description: "Что проверяет ai_stp, какие движки использует и какие риски снижает каждая проверка."
---

Эта страница — вид help-центра на то, что реально просканировали карточка каталога, план публикации и pin сетапа. Восемь [видов компонентов](components/index.md) и [линии доверия](trust-and-safety/index.md) ссылаются сюда и таблицу не копируют.

Перед подтверждением публичного компонента ai_stp запускает поэтапный набор статических проверок без исполнения компонента. Успешный результат снижает известные риски, но не гарантирует полную безопасность. Провал или отсутствие обязательной проверки блокирует публикацию; необязательные проверки дают видимое предупреждение или неполное покрытие.

## Состояния результата

- **Пройдена** — движок завершился без находок по политике.
- **Провалена** — найдена блокирующая проблема; каталог показывает очищенную причину.
- **Предупреждение** — неблокирующая находка требует оценки.
- **Не запускалась / degraded** — движок не дал вердикт; обязательное покрытие остаётся незавершённым. Необязательные незавершённые проверки остаются в машинном аудите и не входят в процент карточки.
- **Неприменима / skipped** — проверка неприменима и не входит в процент.

Процент на карточке каталога: `passed / (passed + failed + warning)`. Публикация
смотрит на обязательные проверки; дополнительные сканеры показываются отдельно,
если у них есть вердикт.

## Что говорит карточка

Процент — покрытие **завершённых** обязательных или показанных проверок, не
оценка безопасности байтов. Карточка со 100% всё ещё может быть объектом
`experimental`, а верифицированный автор — владеть версией, у которой
обязательная проверка провалилась.

| Что видно | Что это значит | Чем это не является |
| --- | --- | --- |
| высокий процент | большинство показанных проверок дали `passed` | workflow безвреден |
| `failed` | есть блокирующая находка | надо «сильнее» нажать `--confirm` |
| `warning` | нужна оценка | публикация уже разрешена |
| `not run` / degraded | движок не дал вердикт | проверка прошла отсутствием |
| `skipped` | проверка неприменима | семейство нарочно проигнорировали |

`author_verified` и `component_verified` независимы от этой таблицы.
Процент скана — не один из этих битов. Закрепляйте точный `X.Y` и читайте
id проверок; не ставьте по заголовочному числу.

## Что делать с `not run`

Обязательная проверка, которая не может выполниться, **блокирует
публикацию**. Это не мягкий skip. Необязательный сканер, которого нет в
установке, остаётся в машинном аудите и никогда не становится pass.

Если карточка показывает degraded coverage:

1. скопируйте id проверки (каталог очищает причину);
2. найдите семейство в этой таблице;
3. подайте [жалобу](web/reports.md) на этот дайджест или дождитесь, пока
   движок станет доступен и версию просканируют снова.

Не считайте отсутствующий прогон NVIDIA SkillSpector или Cisco Skill
Scanner за пройденный `skill_static_gate`. Собственные правила всё равно
работают; внешние движки — добавка, когда они есть.

## Полный перечень

| Семейство                   | Проверки                                                                                            | Метод или технология                                                                                                                                                                                                                                                                               | Какой риск снижает                                                                                        |
| --------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Целостность и происхождение | `structure`, `digest`, `license`, `tags`, `source_repo`                                             | Pydantic schemas, canonical serialization, SHA-256, закрепление repository/commit                                                                                                                                                                                                                  | Подмена артефакта; OWASP A08 Software and Data Integrity Failures                                         |
| Безопасная распаковка       | `artifact_unpack`, `path_denylist`                                                                  | Ограниченная распаковка, нормализация путей, deny rules                                                                                                                                                                                                                                            | Zip-slip, traversal и опасные файлы; A01 Broken Access Control, A08                                       |
| Секреты                     | `secrets_heuristic`, `secrets_gitleaks`                                                             | Собственные правила и [Gitleaks](https://github.com/gitleaks/gitleaks)                                                                                                                                                                                                                             | Токены, пароли и private keys; A02 Cryptographic Failures                                                 |
| Prompt и скрытый контент    | `pi_content_pack`, `content_hidden`                                                                 | Собственные правила prompt injection и invisible content                                                                                                                                                                                                                                           | Скрытые инструкции; OWASP LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure                  |
| Общий SAST                  | `sast_opengrep`                                                                                     | Собственные правила через [Opengrep](https://github.com/opengrep/opengrep)                                                                                                                                                                                                                         | Injection, небезопасные subprocess и паттерны кода; A03 Injection, A04 Insecure Design                    |
| MCP и hooks                 | `mcp_config_static`, `hook_schema_static`, `hook_command_argv`                                      | Schema validation, transport policy, анализ argv                                                                                                                                                                                                                                                   | SSRF, command injection, избыточные возможности; A03, A10 SSRF, LLM06 Excessive Agency                    |
| Agent skills                | `skill_static_gate`                                                                                 | Собственные правила, [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector), [Cisco Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner)                                                                                                                                       | Вредоносные инструкции, утечка данных и скрытые полномочия; LLM01, LLM02, LLM06                           |
| SAST по языкам              | `shell_obfuscation`, `sast_shellcheck`, `sast_bandit`, `sast_gosec`, `sast_eslint_security`         | [ShellCheck](https://github.com/koalaman/shellcheck), [Bandit](https://github.com/PyCQA/bandit), [gosec](https://github.com/securego/gosec), [eslint-plugin-security](https://github.com/eslint-community/eslint-plugin-security)                                                                  | Injection и небезопасные паттерны языка; A03, A04                                                         |
| Зависимости                 | `sca_osv`, `sca_pip_audit`, `sca_govulncheck`, `sca_cargo_audit`, `sca_cargo_deny`, `sca_npm_audit` | [OSV-Scanner](https://github.com/google/osv-scanner), [pip-audit](https://github.com/pypa/pip-audit), [govulncheck](https://github.com/golang/vuln), [cargo-audit](https://github.com/rustsec/rustsec/tree/main/cargo-audit), [cargo-deny](https://github.com/EmbarkStudios/cargo-deny), npm audit | Известно уязвимые зависимости; A06 Vulnerable and Outdated Components, LLM05 Supply Chain Vulnerabilities |
| Документы                   | `document_pdf`                                                                                      | Статический поиск PDF actions, JavaScript и подозрительных строк                                                                                                                                                                                                                                   | Активный контент и embedded prompt injection; A03, LLM01                                                  |
| Malware                     | `malware_clamav`, `malware_yara`                                                                    | [ClamAV](https://github.com/Cisco-Talos/clamav), [YARA](https://github.com/VirusTotal/yara)                                                                                                                                                                                                        | Известное malware и сигнатуры политики; A08                                                               |
| Сетапы                      | `setup_pin_aggregate`                                                                               | Точные pins и агрегированные доказательства компонентов                                                                                                                                                                                                                                            | Непроверенная зависимость внутри сетапа; A06, A08, LLM05                                                  |

Набор зависит от вида компонента, найденных языков и файлов, а также профиля `minimal`, `standard` или `strict`. Внешние CLI-движки запускаются только при разрешении платформы; недоступный движок никогда не считается успешно пройденным.

## Почему проверка не прошла

В развёрнутом виде каталог показывает очищенную причину для `failed`, `warning`, `degraded` и `not_run`. Секреты, чувствительные значения и локальные пути не публикуются. При обращении к автору укажите технический идентификатор проверки.

Нормативная политика принадлежит `docs/contracts/validation-policy.md`; эта страница — её версия для читателя.

## Связанные страницы

- [Доверие и безопасность](trust-and-safety/index.md) — две оси verification, не этот процент.
- [Каталог](catalog/index.md) — как карточка показывает результат.
- [Компоненты](components/index.md) — виды, которые выбирают набор проверок.
- [Публикация](publishing/index.md) — обязательные сканы, которые блокируют публичную версию.
- [Жалобы](cli/report.md) — подать случай с идентификатором проверки.
