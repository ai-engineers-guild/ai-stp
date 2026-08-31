---
description: "The voice, tone, markers, and identity rules of the ai_stp product."
last_verified: "2026-08-22"
---

# ai_stp — brand

## Setup passports for AI harnesses

A unified layer for selecting, assembling, and safely managing the lifecycle of AI harness configurations: passports, a catalog, trust lines, and installation through verified providers.

## The system in one line

An almost-black machine canvas, ink surfaces, white primary and gray secondary text, gray `1px` lines, and a single signal orange (`#fb631b`) with IBM Plex Sans and IBM Plex Mono typefaces — light human and dark machine modes.

## Product mark

| Element | Rule |
| --- | --- |
| Wordmark | `ai_stp` in product UI (sans, medium weight) |
| Primary mark | Abstract **5-node loop** (club of five / human-in-the-loop). Diagonal gradient: soft orange `#f4793f` → signal `#fb631b` → plum `#b0486e` → violet `#62347a` → deep `#2d1c4e`. Ship-wheel only as metaphor — reads as tech ring / network, not a literal helm |
| Background | **Transparent** always (no plate). Works on machine dark and human light |
| Safe-zone | ~14% padding each side; `outer_r + node_r < size/2 − edge`. Nodes must never touch canvas edge |
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

In human mode: `#ffffff` canvas, `#181818` ink text, `#f9f8f4` sand surface, `#d4d2cb` light line.

## Typography

- **Display / body:** plexSans (400, 500) — self-host `apps/web/public/fonts/plex-sans-*.woff2`
- **Mono:** plexMono (400, 500) — ids, versions, install commands, technical meta — `plex-mono-*.woff2`
- Fallbacks: Arial / system-ui (sans); ui-monospace stack (mono)
- Both typefaces are IBM Plex under the SIL Open Font License 1.1, from one superfamily, and both support Cyrillic.
  They replaced Gerstner Programm and FT System Mono, whose own metadata prohibits
  storage on public servers and distribution — exactly what this repository does
  once it becomes public. The replacement was found through `just fonts-licence`; it also
  fixed the Cyrillic interface, which silently fell back to Arial with the previous pair.

## Voice

A precise, composed, signal-rich voice. It addresses developers and their coding agents assembling complete harness setups, without marketing fluff.

### Pillars

- Setup passports instead of scattered snippets
- Filtered trust lines
- Agent-first CLI, human confirmation for risk
- Local mode, public catalog, and synchronization after sign-in — three clear modes
- Origin and verification are visible, not buried

**Prefer:** passport, setup, component, harness, trust line, verified author, installation, device, grant, revision
**Avoid:** magical AI, unlimited intelligence, synergy, disrupt, game-changing, chatbot fluff

## Imagery

Product UI modules, catalog cards, trust badges, installation blocks, and monospaced technical labels. Photographs are rare. High black-and-white contrast with an orange CTA signal. The orange→deep-violet gradient is used only within the mark; page CTAs remain solid signal orange without a background fill.

## Layout rules

- Base radius 8px; controls 4px; labels 6px; large blocks up to 24px
- 1px borders; 8px spacing baseline
- Dual human / machine modes
- One primary orange CTA per viewport; the accent is a signal, not a fill

## CTA patterns

- Open catalog
- Sign in
- Install CLI
- Copy install command
- Apply filters

## Agent implementation notes

1. Bind color roles from `apps/web/src/theme/tokens.json` into CSS variables (`globals.css`).
2. Self-host IBM Plex Sans + IBM Plex Mono; map `--font-sans` and `--font-mono`.
3. Prefer dark machine mode for dense product UI; human light for marketing/landing.
4. Use orange sparingly; secondary text is muted; do not allow light-on-light or dark-on-dark.
5. Components use only semantic utilities (`bg-primary`, `text-muted-foreground`) with no raw hex in React.
