# Recover

User intents: it timed out, partial install, stuck operation.

First command: `ai-stp task intents --json`. Do not dump machine help.
Do not type `ai-stp help` or `help --json`. Do not type `ai-stp capabilities`.
Do not invent `task get` or `task status`.

If an install task is still `planned`, `blocked`, or `running`, continue that
task. Do not start a second `install` intent. Do not dump the full registry.

Expert recovery after the task already failed: `ai-stp install recover` or
`ai-stp install resume` when the CLI names them. Establish the actual effect
first. Do not repeat `ai-stp install apply` “to sync”. Use the recovery or
resume command the envelope still offers.

Do not type `setup preserve recover`. Recovering a saved native setup is the
`switch` intent. `ai-stp install recover` or `ai-stp install resume` remain
expert recovery after an install task already failed, when the CLI names them.

A held child `operation_…` on an open install task is resumed by continue, not
by a second start.
