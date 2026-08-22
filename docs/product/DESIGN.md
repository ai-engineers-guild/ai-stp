---
description: "Визуальная дизайн-система web MVP: токены, типографика, компоненты, режимы."
last_verified: "2026-08-22"
---

# ai_stp — дизайн-система

> Surface: web (`apps/web`)  
> Source of truth: `apps/web/src/theme/tokens.json`  
> Runtime CSS: `apps/web/src/app/globals.css`  
> Brand voice: [BRAND.md](BRAND.md)

Плотный product UI для каталога, аккаунта, устройств и путей установки. Два режима: светлый **human** и тёмный **machine**.

## Цветовая палитра

| Role | Name | Hex | Usage |
| --- | --- | --- | --- |
| background | Machine canvas | `#101010` | Dark product canvas |
| surface | Ink surface | `#181818` | Raised panels, cards (dark) |
| foreground | White | `#ffffff` | Primary text on dark |
| muted | Grey 600 | `#858483` | Secondary labels, meta |
| border | Grey 800 | `#434343` | Hairlines (machine) |
| accent | Signal orange | `#fb631b` | CTA, links, focus, active markers |
| accent-secondary | Signal orange hover | `#f4793f` | Primary hover |

Human режим: белый холст `#ffffff`, чернильный `#181818`, песочный `#f9f8f4`, светлая граница `#d4d2cb`.

Семантические HSL-каналы находятся в `tokens.json` под `color.*` для светлой и тёмной темы. Код продукта использует роли (`primary`, `muted-foreground`, `border`), а не raw hex.

Цвета состояний (`error`/`success`/`warning`) находятся в том же файле токенов для форм и trust feedback.

## Типографика

| Role | Family | Weights | Use |
| --- | --- | --- | --- |
| Display / UI | plexSans | 400, 500 | Headings, body, controls |
| Mono | plexMono | 400, 500 | Stable ids, versions, install code, technical meta |

Шкала размеров: 12 · 14 · 16 · 18 · 20 · 24 · 30 (токены в CSS).

Обе гарнитуры — IBM Plex под SIL OFL 1.1, разбиты по `unicode-range`, поэтому латинская
страница не тянет кириллические начертания. Причина замены и её проверка — в
[BRAND.md](BRAND.md) и в комментарии `apps/web/src/app/globals.css`.

## Компоновка

| Token | Value | Use |
| --- | --- | --- |
| Radius base | 8px (`0.5rem`) | Cards, panels |
| Radius sm | 4px | Buttons, inputs, selects |
| Radius md | 6px | Badges / chips |
| Radius xl | 16px | Large shells |
| Border | 1px | Never thick frames |
| Space baseline | 8px | 2 / 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48… |
| Content width | `max-w-6xl` | App shell main |
| Horizontal pad | 16–24px | Header and main |
| Узкий публичный экран | 360–430 px | лендинг, каталог, карточка объекта, вход, аккаунт |

На 360–430 px документ не даёт горизонтальный выход за край; действие
установки и просмотра исходников остаётся видимым; основные действия на
странице объекта и в оболочке имеют цель 44px. Мобильная навигация и
уточнение выдачи сохраняют клавиатуру и видимый фокус. Исполнимые критерии —
`SPEC-022`, `SPEC-023`, `SPEC-034`, `SPEC-037`.

### Правила подачи

1. Две независимые оси отображения: проекция `human`/`machine` и цветовая тема `light`/`dark`. Кнопка темы меняет только цвета. Проекция является адресуемым маршрутом и отдельным серверным документом по `ADR-0076` и `SPEC-036`, а не стилизацией человеческого дерева: закреплённый внизу переключатель ведёт на парный URL. Machine использует моноширинную подачу и текстовый документ, где Markdown-маркеры заголовков и ссылки являются содержимым, а декоративные медиа отсутствуют.
2. Accent orange применяется только для сильного сигнала: CTAs, focus rings, брендовой полосы и key active dots. Полноэкранные заливки запрещены.
3. На viewport для одного действия остаётся одна сплошная primary button.
4. Hover не делает primary text серым: меняется fill/border, foreground contrast остаётся не ниже default.
5. Every focusable control has a visible `:focus-visible` ring using `--ring` (accent).
6. Mono применяется для machine labels; декоративные emoji не используются как functional icons.
7. Icons only from `src/theme/icons.tsx` registry.

## Набор компонентов React

Path root: `apps/web/src/components/`

### Atoms

| Component | File | Notes |
| --- | --- | --- |
| Button | `atoms/button.tsx` | default / secondary / outline / ghost / destructive; sizes sm · default · lg · icon |
| Badge | `atoms/badge.tsx` | mono chips, radius md |
| Input | `atoms/input.tsx` | radius sm, 1px border |
| Textarea | `atoms/textarea.tsx` | same as input |
| Label | `atoms/label.tsx` | Radix label |
| Skeleton | `atoms/skeleton.tsx` | muted pulse |
| Dialog | `atoms/dialog.tsx` | Radix dialog shell |

### Molecules

SearchField · StatePanel · ThemeToggle · RouteLoading · DetailAccordion · PassportJsonViewer · CatalogAuthorLink · ObjectTechnicalDetails · RequirementsSummary · ObjectVersionHistory

### Organisms

ObjectCard · CatalogFilters · CatalogResults · InstallBlock · DeviceList · IdentityList · ProfileForm · ObjectDetailHeader · ObjectDetailFrame · ComponentMediaGallery

### Layouts

AppShell · SiteHeader · MachineHeader · MachineIndex · MachineFooter

## Storybook

```bash
cd apps/web
bun run storybook
bun run build-storybook
```

Groups: Foundations · UI Kit / Atoms · Molecules · Organisms · Layouts. Toolbar switches light/dark.

## Изменение темы

1. Edit `apps/web/src/theme/tokens.json`.
2. Mirror channels into `globals.css` (`:root` / `.dark` and `@theme inline`).
3. Keep React on semantic utilities only.
4. Rebuild Storybook to verify foundations and kit stories.
