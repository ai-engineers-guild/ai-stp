---
description: "Skill components: repeatable workflows for an agent."
---

# `skill`

A `skill` is a portable agent workflow. It usually holds a `SKILL.md`,
instructions, references, assets and sometimes scripts that help an agent carry
out a specialised task without guessing at the process.

A skill answers the question: "how should the agent do this class of task?"

## How a skill differs from its neighbours

| Kind | The main difference |
| --- | --- |
| `instruction` | gives general rules and context, and need not describe a workflow |
| `command` | runs as a named shortcut, while a skill activates on the meaning of the task |
| `plugin` | extends the harness itself, while a skill extends the agent's working behaviour |
| `mcp` | gives a tool interface, while a skill explains when and how to use it |

## How a skill moves through `ai_stp`

=== "Author"
    The author publishes the skill from a public GitHub source, or imports it
    locally. The version pins an exact commit and subpath.

=== "Catalog"
    The catalog shows what it is for, the supported harnesses, the constraints,
    the author's trusted status and the component's own independent status.

=== "Compiler"
    The compiler checks that the skill can be built into the chosen setup and
    that its file structure suits the provider's projection.

=== "Provider"
    The provider places the skill in the harness's native directory and updates
    the related indexes only after a plan, a digest and a confirmation.

## What to look at before installing

| Check | Why it matters |
| --- | --- |
| Are there scripts | scripts can act outside the Markdown |
| Are there references or assets | the agent needs the whole set, not only `SKILL.md` |
| Is the harness compatible | the same skill name does not guarantee the same format |
| Who is the author | a verified author does not make content automatically safe |
| Which version is pinned | updating a skill makes a new version of the setup |

??? question "Can a skill be used without publishing it"
    Yes. Your own, imported or exactly pinned skill can be used after local
    checks. It does not thereby become platform-verified, and it must be shown
    as exactly what it is: a local or pinned object.
