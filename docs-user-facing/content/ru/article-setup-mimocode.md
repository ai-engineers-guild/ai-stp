---
type: article
slug: setup-mimocode
locale: ru
title: "MiMoCode"
description: "Система из открытой линейки NDDev OpenNetwork; поддержка как отдельного harness в ai-stp ещё не заявлена."
published_at: 2026-09-04
tags: [setup, mimocode, harness]
draft: false
---

# MiMoCode

![Профиль MiMoCode](/content/illustrations/nddev-builder.jpg)

MiMoCode — система из открытой линейки NDDev OpenNetwork. В текущем контракте ai-stp она не заявлена как отдельный harness: закрытый supported set содержит семь setup-system — Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor и Antigravity. Поэтому эта статья описывает границу поддержки, а не обещает автоматическую установку MiMoCode.

## Что можно утверждать о setup

У MiMoCode может быть собственная нативная структура, но в этом репозитории для неё нет утверждённого discovery catalog, provider surface и публичного `mimocode-setup-system`. Нельзя безопасно угадывать, куда класть `instruction`, `skill`, `agent`, `plugin`, MCP или settings, даже если названия каталогов похожи на другие harness.

| Слой | Статус | Что нужно до поддержки |
| --- | --- | --- |
| Harness identity | Вне закрытого supported set | Зафиксировать детектор и точный продуктовый контракт |
| Native surfaces | Не заявлены | Подтвердить global/project layout и component kinds |
| Setup assembler | Не заявлен | Добавить совместимые projection rules и проверки |
| Provider | Не заявлен | Публичный versioned provider с protocol и rollback |

## Как это связано с ai-stp

ai-stp может хранить описание и ссылку на внешний проект, но не должен выдавать MiMoCode за verified setup. Для семи поддержанных harness CLI обнаруживает компоненты, создаёт passports, проверяет граф, собирает exact plan и передаёт запись соответствующему NDDev provider. Для MiMoCode пока доступен только безопасный read-only обзор.

## Что нужно для добавления

1. Описать native layout и scopes MiMoCode.
2. Подтвердить, какие типы компонентов реально читает продукт.
3. Выпустить `mimocode-setup-system` с versioned protocol, manifest и rollback.
4. Добавить evidence, projection rules, docs и тесты, после чего расширить closed set отдельным решением.

До этого не переносите в MiMoCode весь пользовательский home и не ставьте найденный пакет автоматически: похожее имя каталога не является доказательством совместимости.

## Ссылки

- [Организация NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork)
- [Контракт публичных setup-system в ai-stp](https://github.com/NDDev-OpenNetwork/ai-stp/blob/main/specs/active/SPEC-008-provider-installation.md)

## Граница доверия

Статья намеренно отделяет внешний проект от verified support. Пока нет declared surface, exact provider и evidence, MiMoCode нельзя включать в автоматический selection или installation flow.

> Сначала upstream-контракт и измерение native surface, затем passport и provider. До этого — только обзор и ручная проверка.
