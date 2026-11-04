---
title: "Troubleshooting"
description: "Inspect native state and recover the original operation."
---

# Troubleshooting

```sh
ai-stp version --json
ai-stp doctor --json
ai-stp configuration native pending --json
```

Use the original state directory. For a task, read its current revision with
`task status`. For native configuration, retain the operation ID and plan digest
reported by `pending` and read scoped help for recovery. A preparation can require
the original consumer to exit before application.

For a missing executable or a Python registry, follow the
[installation and migration guide](../quickstart/human.md). For sign-in errors,
read account status and start a new authorization if its code expired.
