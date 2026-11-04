---
title: "Quickstart for agents"
description: "Use the current command registry and resume the original operation."
---

# Quickstart for agents

Read the task registry for authoring and scoped help for first-party setup
configuration:

```sh
ai-stp task intents --json
ai-stp task input-schema --intent author --json
ai-stp help --path "configuration native" --json
```

For a new setup, use `configuration native` with the exact setup version,
passport digest and target roots. Review the returned plan, then prepare and
apply it with the original digest. Follow the restart instructions when the
plan requires handoff. See the [setup procedure](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md#setup-configuration).

For task continuations, execute resolved argv when `actor` is `cli`. After an
interruption, read the original task or native operation before retrying. Keep
the same state directory, task revision or operation ID, and plan digest.
