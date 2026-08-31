---
description: "Decision on product languages: web and the skill are bilingual, while launch catalog content is English."
last_verified: "2026-08-04"
---

# ADR-0035: Product and launch catalog languages

Status: accepted.

## Context

Repository documentation is written in Russian, as established by `AGENTS.md`. But the language of the product itself was never decided: the language of the web, canonical Agent Skill, and—most importantly—launch catalog object content. For a product whose primary consumer is a coding agent, the language of component instructions and descriptions directly affects work quality: modern agents follow English instructions more reliably and match English descriptions to requests more accurately.

## Options

1. Russian everywhere. Consistent with documentation, but reduces agent quality with first-party objects and narrows the catalog audience.
2. English everywhere. Maximum agent quality, but user-facing surfaces lose the Guild's native language.
3. Split by consumer: human-facing surfaces are bilingual; agent content is English.

## Decision

Option 3 is accepted.

**Web and the canonical Agent Skill are available in Russian and English from launch.** Both locales have equal standing; skill projections for five harnesses are generated in both locales from one canonical source.

**Launch catalog object content is English.** Instructions, descriptions, skill texts, and other content of first-party components and setups from `ADR-0034` are written in English: an agent reads and executes them, and English provides better instruction-following quality.

**User publications remain in the author's language.** The platform imposes no language requirement on third-party objects; language is a content property, not a publication condition.

**Repository documentation does not change.** Prose documents in `ai_stp` remain Russian under `AGENTS.md`; that is a repository rule, not a product rule.

## Consequences

- the MVP boundary describes the Agent Skill as bilingual rather than Russian;
- web receives a two-locales-from-launch requirement;
- the launch catalog release barrier establishes English for object content;
- machine contracts are unaffected: identifiers, states, and codes remain Latin-script under existing rules.

## Reconsideration conditions

This decision will be reconsidered if measured evidence shows that bilingual object content does not degrade agent performance, or if the catalog audience requires a third surface locale.
