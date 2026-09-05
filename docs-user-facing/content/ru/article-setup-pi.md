---
type: article
slug: setup-pi
locale: ru
title: "Pi"
description: "Минимальный harness с package resources, skills, extensions, prompts и target settings"
published_at: 2026-09-04
tags: [setup, pi, harness]
draft: false
---

# Pi

![Профиль Pi](/content/illustrations/setup-pi.jpg)

Pi — минималистичный локальный coding-agent. Его сильная сторона — прозрачный слой resources: skills и prompt templates подключаются из каталогов или package, а настройки явно задают, какие extensions и модели доступны. Это делает setup маленьким и обозримым, но требует не приписывать Pi возможности другого harness.

## Нативная поверхность

| Область | Что читает Pi | Как это отражается в ai-stp |
| --- | --- | --- |
| Пользователь | `~/.pi/agent/AGENTS.md`, `skills/`, `extensions/`, `prompts/`, `settings.json`, `models.json` | Global instruction, skill, plugin, command и setting |
| Проект | `.pi/skills/`, `.pi/extensions/`, `.pi/prompts/`, `.pi/settings.json` | Проектные resources после trust проекта |
| Package | npm/git package с resources | Переносимая упаковка skills и extensions |
| MCP | Отдельного документированного нативного MCP-конфига нет | Интеграция должна идти через extension/package, а не через выдуманный MCP-файл |

Pi использует `AGENTS.md` как instruction, но проектный override может изменить порядок загрузки. Project resources также зависят от решения trust: наличие `.pi/settings.json` ещё не означает, что Pi автоматически разрешит его содержимое.

## Как собирается setup

1. `ai-stp` отделяет authored resources от `auth.json`, model store, cache и session state.
2. Passport фиксирует точный package или локальный источник, scope и роль каждого компонента.
3. Ассемблер проверяет, что skill, prompt, extension и setting попадают в поддержанную Pi-поверхность.
4. Публичный `pi-setup-system` получает exact plan и пишет только целевой каталог Pi. Сайт не запускает Pi и не меняет его active session.

В терминах каталога Pi: skill — on-demand workflow, plugin — extension/package, command — prompt template, setting — JSON-профиль, а MCP не объявляется отдельным нативным типом.

## Когда выбирать Pi

Pi подходит для компактного локального setup, где важны package resources, skills и ручной контроль настроек. Для команды удобно держать `.pi/` рядом с проектом и отдельно проверять trust перед включением extensions.

## Ссылки

- [Настройки Pi](https://pi.dev/docs/latest/settings)
- [Skills в Pi](https://pi.dev/docs/latest/skills)
- [Безопасность Pi](https://pi.dev/docs/latest/security)
- [Публичный pi-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/pi-setup-system)

## Граница доверия

Pi — локальный агент без встроенного sandbox, поэтому skill, package и extension нужно читать до включения. Tier поддержки ai-stp не заменяет review содержимого, pin версии и rollback.

> Наблюдение → passport → trust проекта → проверка resources → exact plan → установка provider.
