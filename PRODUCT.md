# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a developer configuring a coding agent who wants to select, validate, and safely install a complete setup for a specific AI harness. Component and setup authors also use the web, while machine clients read public catalog information.

## Product Purpose

`ai_stp` unifies passports, the catalog, trust lines, compatibility validation, and the secure lifecycle of AI harness configurations. Success means that a person quickly understands an object's origin and constraints, while an agent receives the same public facts in a predictable machine-readable form without separate business logic.

## Positioning

The product is not another snippet catalog: it deterministically assembles complete setups from exactly pinned component versions, applies mechanical constraints before agent reasoning, and delegates writing the final state exclusively to the public provider for the specific harness.

## Operating Context

The primary flow spans the CLI, coding agent, local registry, public web catalog, and harness provider. An anonymous visitor reads the catalog and profiles; after signing in, a user manages the account, devices, privacy, and publications. The Russian and English locales are equal.

## Capabilities and Constraints

- Primary support: Claude Code, Codex, and Grok Build; Pi, OpenCode, Cursor, and Antigravity are in beta; an unknown harness is available in limited `undefined` mode.
- The web displays results and manages the account and public catalog, but does not assemble or install setups.
- Public data must be available to people, search engines, and LLM clients without exposing private records.
- Human/Machine are two equal projections of the same information: Human is optimized for human reading, while Machine provides technical presentation and explicit links to machine-readable resources. The projection is independent of the light or dark color theme; switching it does not change server truth or create a separate domain model.
- The contact email is currently an explicit configuration placeholder and must be replaced by the environment before production launch.
- All external writes require a plan, digest, precondition revalidation, and explicit confirmation; the UI does not bypass these constraints.

## Brand Commitments

The `ai_stp` name, five-node loop mark, signal-orange accent, Gerstner Programm and FT System Mono, precise engineering voice, and existing human/machine semantics are preserved. Parallel and Nace set the level of composition, mode switch, keyboard navigation, and footer density, but their brands, copy, and visual assets are not reproduced.

## Evidence on Hand

- Normative product and architecture documents are in `docs/`; active requirements are in `specs/active/`.
- The design system and brand are described in `docs/product/DESIGN.md` and `docs/product/BRAND.md`.
- The Next.js implementation is in `apps/web`; portable tokens are in `apps/web/src/theme/tokens.json`.
- The user provided screenshots of the Parallel/Nace switch and footer. There is no real feedback, commercial metrics, or production contact email; they must not be invented.

## Product Principles

- Each fact has one owner and one domain interpretation.
- Origin, verification, support status, and constraints are visible, not hidden.
- Human confirmation remains mandatory for unknown and risky actions.
- The machine-readable surface is a first-class part of the product, not SEO decoration.
- Private data does not enter public HTML, the client bundle, logs, or metadata.

## Accessibility & Inclusion

The interface must support keyboard use, visible focus, reduced motion, mobile layout, semantic roles, and WCAG 2.2 AA. The Russian and English versions carry equivalent meaning and behavior.
