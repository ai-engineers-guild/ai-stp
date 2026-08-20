---
description: "Голос, тон, маркеры и правила идентичности продукта ai_stp."
last_verified: "2026-08-07"
---

# ai_stp — бренд

## Паспорта сетапов для AI-харнессов

Единый слой подбора, сборки и безопасного жизненного цикла конфигураций AI-харнессов: паспорта, каталог, линии доверия, установка через проверенные провайдеры.

## Система одной строкой

Почти чёрный машинный холст, чернильные поверхности, белый основной и серый вторичный текст, серые линии `1px` и один сигнальный оранжевый (`#fb631b`) с гарнитурами Gerstner Programm и FT System Mono — светлый human и тёмный machine режимы.

## Знак продукта

| Element | Rule |
| --- | --- |
| Wordmark | `ai_stp` in product UI (sans, medium weight) |
| Primary mark | Abstract **5-node loop** (club of five / human-in-the-loop). Diagonal gradient: soft orange `#f4793f` → signal `#fb631b` → plum `#b0486e` → violet `#62347a` → deep `#2d1c4e`. Ship-wheel only as metaphor — reads as tech ring / network, not a literal helm |
| Background | **Transparent** always (no plate). Works on machine dark and human light |
| Safe-zone | ~14% padding each side; `outer_r + node_r < size/2 − edge`. Nodes must never touch canvas edge |
| Tagline RU | **Клуб из пяти — human in the loop** |
| Tagline EN | **Five in the loop — a human crew group** (loop / group rhyme) |
| Engineering line | **Hand to hand harness engineering** |
| Favicon | `apps/web/src/app/icon.png` (32) + `icon.svg` + `apple-icon.png` (180); mirror `public/brand/favicon-32.png` |
| Brand kit | `apps/web/public/brand/` — transparent SVG + PNG sizes (see `docs/product/logos/ICON_SIZES.md`) |
| Docs mirror | `docs/product/logos/` (same assets + size table) |
| Header | `SiteHeader` uses `/brand/logo-mark.png` (128, transparent) + wordmark `ai_stp` |
| Do not | Partner/harness logos as product marks; emoji as brand icons; literal Dutch helm; solid plate behind the mark; hard crop of nodes; pure neon magenta spectrum (use muted plum→deep violet) |

## Color roles

| Role | Hex | Use |
| --- | --- | --- |
| Background (machine) | `#101010` | Default product / dark canvas |
| Surface | `#181818` | Cards, raised panels |
| Foreground (on dark) | `#ffffff` | Primary text on machine |
| Muted | `#858483` | Secondary labels, meta |
| Border | `#434343` | Hairlines, dividers (machine) |
| Accent | `#fb631b` | Primary CTA, focus ring, active signals |
| Accent hover | `#f4793f` | Primary hover / soft brand emphasis |

В human режиме: холст `#ffffff`, чернильный текст `#181818`, песочная поверхность `#f9f8f4`, светлая линия `#d4d2cb`.

## Типографика

- **Display / body:** gerstnerProgramm (400, 500) — self-host `apps/web/public/fonts/Gerstner_Programm*.woff2`
- **Mono:** ftSystemMono (400, 500) — ids, versions, install commands, technical meta — `FTSystemMono_*.woff2`
- Fallbacks: Arial / system-ui (sans); ui-monospace stack (mono)

## Голос

Точный, собранный и насыщенный сигналами голос. Он обращается к разработчикам и их coding agents, собирающим полные сетапы харнессов, без рекламной шелухи.

### Опоры

- Паспорта сетапов вместо разрозненных вставок
- Линии доверия с фильтрацией
- Agent-first CLI, human confirmation for risk
- Локальный режим, публичный каталог и синхронизация после входа — три ясных режима
- Origin and verification are visible, not buried

**Предпочитать:** паспорт, сетап, компонент, харнесс, линия доверия, подтверждённый автор, установка, устройство, grant, revision
**Avoid:** magical AI, unlimited intelligence, synergy, disrupt, game-changing, chatbot fluff

## Образы

Модули product UI, карточки каталога, бейджи доверия, блоки установки и моноширинные технические метки. Фотографии редки. Высокий чёрно-белый контраст с оранжевым CTA-сигналом. Градиент orange→deep-violet применяется только внутри знака; page CTAs остаются сплошным сигнальным оранжевым без заливки фона.

## Правила компоновки

- Базовый радиус 8px; элементы управления 4px; метки 6px; крупные блоки до 24px
- 1px borders; 8px spacing baseline
- Dual human / machine modes
- Один primary orange CTA на viewport; акцент является сигналом, а не заливкой

## Паттерны CTA

- Open catalog
- Sign in
- Install CLI
- Copy install command
- Apply filters

## Заметки по реализации Agent

1. Bind color roles from `apps/web/src/theme/tokens.json` into CSS variables (`globals.css`).
2. Self-host Gerstner + FT System Mono; map `--font-sans` and `--font-mono`.
3. Предпочитать тёмный machine режим для плотного product UI; human light — для marketing/landing.
4. Использовать orange экономно; вторичный текст — muted; не допускать light-on-light или dark-on-dark.
5. Components используют только semantic utilities (`bg-primary`, `text-muted-foreground`) без raw hex в React.
