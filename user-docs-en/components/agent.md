---
description: "Agent components: roles and specialised subagents inside a setup."
---

# `agent`

An `agent` describes the role of a specialised agent or subagent inside a
harness: its area of responsibility, its inputs, its limits, its tools, and the
result expected of it.

An agent component is not a setup of its own. It belongs to one harness's setup
and inherits its boundaries.

## What agent components are for

| Example role | The benefit |
| --- | --- |
| reviewer | separates analysis from implementation |
| docs-writer | keeps documentation style and structure |
| security-checker | focuses on risk rather than on the feature |
| release-helper | works through the release checklist |

## The limits of a role

| Describe | Do not describe |
| --- | --- |
| the purpose of the role | a global replacement for every instruction |
| the tools it may use | secrets or personal tokens |
| what a finished result looks like | an uncontrolled background daemon |
| when to call the role | permission to change the outside world unconfirmed |

??? question "How an agent differs from a skill"
    A skill describes the process for a class of tasks. An agent describes a
    role that can carry out different tasks within its area. In a real setup
    they usually work together: the agent uses the skills that fit.

## How it works in `ai_stp`

1. The agent's passport records the harness, the role, the version and the
   limits.
2. The compiler checks whether the harness supports that agent surface.
3. The provider creates the native description of the role.
4. Status shows which roles are active in the target and where they came from.

!!! warning "Do not widen authority by accident"
    An agent with a vague scope quickly becomes "do everything". For the MVP it
    is better to have fewer roles with clear boundaries and a checkable result.
