---
type: blog_post
slug: skills-as-workflow
locale: en
title: "How to write Agent Skills without making an agent cosplay a junior"
description: "A practical field note on skills as workflows, not folders of Markdown."
published_at: 2026-09-04
tags: [practice, ai, skills-as-workflow]
draft: false
cover_image: /content/illustrations/skills-as-workflow.jpg
cover_alt: "Illustration: How to write Agent Skills without making an agent cosplay a junior"
---

# How to write Agent Skills without making an agent cosplay a junior

![Illustration: How to write Agent Skills without making an agent cosplay a junior](/content/illustrations/skills-as-workflow.jpg)

How to write Agent Skills so that an agent does not cosplay a junior after onboarding

Hello, dear reader. In the previous part, I developed the idea that a skill is a workflow package, not a prompt in a little folder. Now let us talk about why some skills work while others turn into a Markdown folder with hope as the only plan.

The main trick is that the real thing is not only `SKILL.md`, but the Skill + Agent Harness connection. A harness is the runtime around the model: finding skills, choosing the right one, loading instructions, running tools/MCP/shell, permissions, traces, and approvals. [Addy Osmani has a good engineering breakdown](https://addyosmani.com/blog/agent-harness-engineering/).

<u>Progressive disclosure — why skills scale</u>

An agent should not keep the entire corporate knowledge library in its context. At first it sees only `name` + `description`, then, after selection, it loads `SKILL.md`, and only after that it reads `references/`, `assets/`, `examples/`, or runs `scripts/`.

That is exactly why a skill is better than a giant 3,000-line `AGENTS.md`. `AGENTS.md` is always-on background; a skill is an on-demand capability. Codex describes this in its [skills documentation](https://developers.openai.com/codex/skills), and Claude Code documents the same model in its [skills guide](https://code.claude.com/docs/en/skills).

Practical advice: keep the procedure short in `SKILL.md`, and move long policies, API docs, JQL references, report templates, and examples into `references/`, `assets/`, or `examples/`. If `SKILL.md` has swollen into a treatise, you have written a new Confluence.

<u>Description is the main trigger, not decoration</u>

A common mistake is a beautiful skill body with a useless description. The agent chooses a skill precisely by its description, so “Helps with code” is garbage. It is like a Jira ticket named “Make it good”.

A proper description answers: what task the skill performs, when to use it, which words trigger it, what inputs it needs, what result to return, and when NOT to use it.

Bad example: `Helps with project management`

Better: `Checks Jira sprint health, finds blocked issues, stale tasks, missing owners and release risks. Use before daily status update or weekly project report. Do not use for backlog prioritization.`

For design guidance, see Anthropic's [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md).

<u>Write anti-rationalization rules directly into the instructions</u>

An agent likes cutting corners no less than a manager before a Friday demo. It will easily say “the change is small”, “it looks fine visually”, “the tests take too long”, or “the user is in a hurry”. So a skill needs rules against excuses.

Examples:

- if there is a diff, inspect first, then summarize, then plan;
- if an action changes an external system, run a dry-run first;
- if there is a write/delete/update, explicit approval is required;
- if data is missing, return missing context instead of making it up;
- if the scanner did not run, do not write that the check passed.

At Twinby, I would package these things into `jira-daily-radar`, `spec-quality-checker`, `release-readiness`, `browser-manual-test`, and `confluence-sync`. Not “agent, tell me the status”, but a procedure: where to read, what counts as risk, which report format to use, and where a human is needed.

<u>A skill must be tested not only for its result, but also for activation</u>

The minimum set:

- explicit activation test: it was called manually;
- implicit activation test: it was called by a natural request;
- negative test: it did not activate where it should not;
- golden samples: input → expected output;
- unit tests for `scripts/`;
- trace review: the steps that actually ran are visible;
- with/without skill: is there a gain in quality, time, or stability?

For evals, useful OpenAI materials include [this guide](https://developers.openai.com/blog/eval-skills) and [Phil Schmid's breakdown](https://www.philschmid.de/testing-skills).

Practical conclusion

Start with inspection/transformation skills: backlog hygiene, PR review precheck, repo safety scan, spec checker, and meeting notes → actions. Connect action/workflow skills that write to Jira/GitHub/Confluence only after a dry-run, approval, and a clear owner.

P.S. A good skill is boring: it triggers explicitly, checks explicitly, fails explicitly, and asks for approval explicitly. Everything else is usually a LinkedIn demo.
