---
title: "cli"
description: "CLI components: a standalone executable invoked as a process."
---

# `cli`

A `cli` is a standalone program with a process entry point. An agent
discovers, registers, publishes, installs, and invokes it as a process.

A `cli` answers the question: **which shared executable can be run?**

It does not answer "which checkable operation can be called by name?"
([`command`](command.md)). A slash command is a named invocation inside a
harness. A `cli` is a process. It is also not the `ai-stp` control-plane
executable itself — that lives under [CLI](../cli/index.md).

!!! warning "Kind `cli` is not a slash command"

    | Object | Where it lives | Lives in a setup? |
    | --- | --- | --- |
    | Kind `cli` (this page) | one shared executable artifact | yes |
    | Kind `command` | harness slash/prompt surface | yes |
    | `ai-stp …` CLI groups | [CLI map](../cli/commands.md) | no |

    Do not copy the same binary into seven harness layouts. The scaffold is
    portable. Harness integration is process execution, not seven native
    copies.

## Neighbours

| Kind | The main difference |
| --- | --- |
| `command` | a command is invoked by name inside a harness; a `cli` is a process |
| `hook` | a hook starts on a lifecycle event; a `cli` starts when executed |
| `mcp` | MCP speaks a protocol; a `cli` is an ordinary program |
| `skill` | a skill is a procedure the harness attaches; a `cli` is an executable |
| `plugin` | a plugin extends the harness itself; a `cli` is a shared tool |
| `setting` | a setting holds parameters; a `cli` holds a program |

Choose `cli` when the object is a standalone executable. Choose `command`
when a person or an agent should start the work by a slash name.

## Recommended package structure

`cli` is executable. `--language` is one of `python`, `typescript`,
`javascript`, `rust`, `go`, or `dart-flutter`. `--harness` is `portable`.

```text
review-kit/                        # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── src/main.py
```

## Red flags

- Scaffolding `--type command` for a process that is not a slash command.
- Passing a concrete harness variant so the same binary is copied seven times.
- Treating `ai-stp` itself as a catalog `cli` component.
