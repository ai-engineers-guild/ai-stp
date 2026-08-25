---
description: "Сборка, проверка, публикация, отзыв и восстановление Python-релиза."
last_verified: "2026-08-25"
---

# Выпуск Python-пакетов

## Подготовка candidate

На чистом exact SHA все пять публикуемых `project.version` должны совпадать, а их
внутренние `Requires-Dist` должны закреплять эту точную версию. Локальная проверка
без публикации:

```bash
just check
just release-candidate
just release-candidate-install
```

`dist/release-candidate/` содержит десять distributions, детерминированный
`ai-stp-cli.cdx.json`, `release-manifest.json` и `SHA256SUMS`. Builder дважды создаёт
artifacts во временных каталогах и завершает работу отказом при любом несовпадении.
Архивный gate одинаково нормализует разделители и Unicode для wheel/sdist, отклоняет
абсолютные и родительские пути, Windows drive paths, повторы и case collisions, а
также symbolic/hard links, устройства, сокеты и каналы.
Dirty tree по умолчанию запрещён; `--allow-dirty` служит только разработческой
характеризации и не создаёт выпускное доказательство.
Флаг `--replace` заменяет только ранее созданный candidate, у которого manifest и
`SHA256SUMS` полностью покрывают неизменённые обычные файлы. Произвольный,
неполный или изменённый каталог не считается release output и не удаляется.

`release-candidate-install` работает вне исходного дерева, передаёт все пять
внутренних колёс как прямые источники, проверяет их URL по PEP 610 и SHA-256,
запускает `version`, `capabilities` и `help --agent`, затем удаляет программу.
`--find-links` без прямой привязки не является доказательством: при совпадающей
версии разрешитель вправе взять одноимённый пакет из публичного индекса. Точная
версионированная команда для сайта находится в `release-manifest.json` как
`install_command`; до фактической публикации она остаётся метаданными выпуска, а не
обещанием доступности на PyPI.

В GitHub workflow `release-candidate` запускается вручную на выбранном ref. Указывается
точная версия, а ref всегда обязан быть tag `v<version>`; удалённого режима без этой
проверки нет. Artifact attestation считается выполненной только при успешной
job `attest-public-candidate`, а не по наличию workflow-файла.

## Внешние prerequisites публикации

До каждого прогона публикации владелец репозитория отдельно подтверждает:

1. репозиторий публичен;
2. обе job прогона `release-candidate` идут на стандартных GitHub-hosted
   `ubuntu-latest` разными исполнителями: сборка не получает OIDC, заверение
   не делает checkout (`ADR-0048`);
3. environment `pypi` (пакет `foundation`) и `pypi-{package}` для остальных
   четырёх защищены required reviewers и запрещают произвольные branches;
4. PyPI Trusted Publisher для каждого проекта закрепляет owner, repository,
   точное имя workflow `publish-pypi.yml` и своё environment — одно OIDC-имя
   на пакет, потому что Trusted Publisher не разделяет identity внутри одного
   environment;
5. exact-SHA `just check`, Linux x86_64 install evidence, SBOM, checksums и
   provenance зелёные;
6. получено отдельное явное разрешение на фактическую публикацию.

Branch и tag protections в этом списке больше нет: репозиторий их не несёт по
`ADR-0115`. Что осталось обязательным — гейт на точном SHA, потому что он
проверяет дерево, а не разрешение.

## Публикация

Публикует workflow `publish-pypi.yml`. Он запускается вручную
(`workflow_dispatch`) на один пакет за прогон: `foundation`, `passports`,
`assurance`, `contracts` или `cli`. Входы — точная версия без ведущего `v` и
`run_id` прогона `release-candidate`, чьи attested bytes загружаются.

Checkout репозитория нет: задача скачивает artifact того прогона, сверяет все
строки `SHA256SUMS`, отбирает ровно два дистрибутива названного пакета и
загружает их через `pypa/gh-action-pypi-publish`. Используются только
`id-token: write` и официальный action, закреплённый commit SHA; username,
password и API token запрещены.

Environment: `pypi` для `foundation`, `pypi-{package}` для остальных. Порядок
загрузки по-прежнему foundation → passports → assurance → contracts → CLI,
потому что внутренние `Requires-Dist` закрепляют точную версию.

Живой индекс на 2026-08-25: все пять проектов опубликованы как `0.0.3`.

## Отказ и отзыв

- PyPI-файл и версия неизменяемы; повтор с другими bytes запрещён.
- При частичной загрузке оставшиеся пакеты не маскируют несовместимость. Исправление
  получает новую согласованную patch version.
- Скомпрометированный или ошибочный выпуск yanked с публичной причиной; bytes не
  удаляются и исторические checksums сохраняются.
- Trusted Publisher/environment блокируются до расследования; постоянного token для
  ротации нет.
- Последняя известная хорошая версия явно закрепляется в документации установки и
  release manifest. Автоматический downgrade пользовательской установки запрещён.
