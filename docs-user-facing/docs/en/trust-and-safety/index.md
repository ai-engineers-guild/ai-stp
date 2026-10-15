---
title: "Trust and safety"
description: "Provenance, verification and installation boundaries."
---

# Trust and safety

Published setup/component versions are immutable and exact. Mechanical compatibility,
access and trust checks decide whether a candidate can be used. User authorization
does not turn unverified bytes into verified bytes or override a mechanical refusal.

Only the authenticated public installation component writes final harness configuration.
Active-agent changes require staged replacement and restart. The CLI does not install,
pin, update or remove the harness executable. It sends no install telemetry.

Read [security evidence](../security-checks.md) and use the retained operation for
[recovery](../troubleshooting/index.md). Keep credentials out of prompts and logs.
