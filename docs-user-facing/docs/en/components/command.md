---
title: "command"
description: "Command components: named commands for a person and an agent."
---

# `command`

A `command` is a named way into a repeatable action: a slash command, a CLI
alias, an agent command, or another shortcut the harness supports.

It answers the question: "which checkable operation can be called by name?"

## Command, hook or skill?

| What you need | Choose |
| --- | --- |
| A person or an agent starts the action by hand | `command` |
| The action starts automatically on an event | `hook` |
| The agent needs a detailed workflow with rules | `skill` |
| Only a parameter has to change | `setting` |

## What makes a good command

| Property | Why |
| --- | --- |
| A short name | it is easy to call and easy to find |
| An explicit description | the agent does not guess what it is for |
| Bounded arguments | less room for a dangerous call |
| A machine help form | the CLI and the agent read the same thing |
| Checkable output | the result can feed the next step |

=== "For a person"
    A command saves repetition and lowers the load. Instead of a long
    instruction, the user runs a shortcut they understand.

=== "For an agent"
    A command gives a stable path of action. The agent should read the
    available commands from the machine help, not invent them from memory.

## How `ai_stp` applies a command

The compiler checks for name conflicts, harness compatibility and the
permissions required. The provider then creates the native command wherever
that particular CLI expects it.

!!! tip "An MVP rule"
    If a command changes the outside world, it must be legible in the install
    plan and must not get around the general rules: digest, confirmation,
    backup and rollback.
