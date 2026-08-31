---
title: "instruction"
description: "Instruction components: rules, memory and textual constraints for a harness."
---

# `instruction`

`instruction` is the textual part of a setup: rules for how an agent behaves,
project memory, working style, the limits of its authority, and hints for one
particular harness.

An instruction runs no code and connects no external tool. Its power is that it
changes the context an agent decides in.

## When to use it

| Situation | Is `instruction` right | Why |
| --- | --- | --- |
| "Always write commit messages in English" | yes | it is a rule of behaviour |
| "Read the testing guide before backend tests" | yes | it routes attention |
| "Run the scanner before push" | partly | the rule can be written down, but the running belongs in a `command` or a `hook` |
| "Connect the GitHub MCP" | no | that is a separate `mcp` |
| "Store the API token" | no | secrets do not go into a component |

## How it works in `ai_stp`

1. An author publishes or imports an instruction with a passport.
2. The passport records the source, the version, the supported harnesses and
   the scope.
3. The setup compiler checks the instruction against the chosen harness.
4. The provider projects the text onto the native surface: an instruction file,
   a memory surface, or another supported format.

!!! note "Memory is not a component kind"
    Memory, rules, preferences and project conventions are the *content* of an
    `instruction` or a `setting`. There is no `memory` kind in `ai_stp`.

## What gets recorded

| What is recorded | Why |
| --- | --- |
| Provenance | to know who supplied the text, from which commit and path |
| Version | to tell an immutable `X.Y` release from the next one |
| Harness | so Claude-specific text is not applied to an incompatible target |
| Scope | to limit a rule to a project, a user or one setup |
| Trust line | to decide whether it may be shown or installed without manual consent |

??? warning "The main risk"
    An instruction can be harmless text, and it can quietly widen an agent's
    authority. Before installing, read the diff of the content, not only the
    title.
