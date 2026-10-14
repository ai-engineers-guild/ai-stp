---
title: "Troubleshooting"
description: "Basic ai_stp diagnostics and safe recovery after an error."
---

# Troubleshooting

Read the current runtime and command scope first:

```bash
ai-stp version --json
ai-stp doctor --json
ai-stp task list --json
```

If the executable is missing, follow the [native installation guide](../quickstart/human.md).
A Python registry must be explicitly transferred, not initialized again.
For a pending task, use its stored id and current revision. For a pending plan,
reuse its exact plan and digest; do not fabricate another operation over it.
Expired, unadmitted plans must be recreated. Admission preserves forward recovery.

Account errors require account status and a new account plan when appropriate;
reusing an expired browser code cannot renew it. Credentials stay outside logs.
A platform capability refusal is a real boundary: provider execution currently
requires Linux. There is no backup/restore shortcut around failed preconditions.
