---
type: article
slug: kind-skill
locale: en
title: A skill is a workflow package, not a prompt in a folder
description: "Kind skill is a repeatable agent procedure: a trigger, steps, references, and optional scripts. It is not AGENTS.md, not a slash command, and not the CLI Agent Skill."
published_at: 2026-08-19
tags: [component, skill]
draft: false
---

A `skill` answers one question: **how should the agent do this class of task?** It is a portable workflow. The usual package is a `SKILL.md` plus optional `references/`, `assets/`, `scripts/`, and examples. The agent does not keep the whole library in context. It first sees a name and a description. Only after it selects the skill does it load the procedure, and only then the heavy files.

That is the opposite of a 3,000-line instruction file. Standing rules belong in kind `instruction`. A named shortcut belongs in kind `command`. An external tool interface belongs in kind `mcp`. A specialised role belongs in kind `agent`.

![A closed catalog card opening into a procedure with scripts](/content/illustrations/kind-skill.jpg)

## Two different objects named skill

The catalog kind `skill` goes into a setup. The CLI also ships one Agent Skill that teaches an agent how to drive `ai-stp` itself. That object is installed with `ai-stp skill install`, inspected with `ai-stp skill status`, and removed with `ai-stp skill remove`. It is not a catalog component. `ai-stp component skill validate` is not that installer.

If those two collapse in your head, you will look for a setup member that is not there, or you will try to publish the CLI helper as a catalog skill.

## What a good description actually does

The agent chooses a skill from the description, not from the beauty of the body. `Helps with code` is noise. A usable description says which task it performs, which words should trigger it, which inputs it needs, what it returns, and when it must not run.

Progressive disclosure is why skills scale. `SKILL.md` stays a short procedure. Long policies, API notes, JQL, templates, and examples live in `references/` and `assets/`. If the main file has become a new Confluence page, you wrote an instruction and labelled it a skill.

Scripts inside a skill are part of the package. They are also a trust surface: hidden side effects, unpinned dependencies, and network calls belong in the install plan, not in a surprise after apply.

## How it shows up on disk

Exact native paths come from `ai-stp component discover --json`. Each finding carries `layout_source`. Do not copy a neighbour harness's folder because the word `skills` looks familiar.

Shared `.agents/skills` belong to no single harness. Discovery reports them once, with `harness_id=null`. A plugin may *contain* skills; those members stay kind `skill`. The pack around them is kind `plugin`.

The only kind-specific validator in the CLI is `ai-stp component skill validate`. Structural readiness for publication is still `ai-stp component passport validate`. Flags, schemas, and `next_actions` come from `ai-stp help --agent --json`, not from this article.

## See also

- [skill chapter in the help center](https://ai-stp.aiguild.space/en/docs/components/skill)
- [Agent Skills as a supply-chain surface](https://ai-stp.aiguild.space/en/content/article/skills-as-workflow)
- [instruction](https://ai-stp.aiguild.space/en/content/article/kind-instruction) and [command](https://ai-stp.aiguild.space/en/content/article/kind-command)
