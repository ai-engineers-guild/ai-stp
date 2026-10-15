---
title: "Security checks"
description: "What verification evidence proves and what it does not."
---

# Security checks

Inspect evidence for the exact artifact, target and policy. Author identity and
component verification are independent. A passing scan is evidence within that
check's scope, not a guarantee about every possible behavior.

An unavailable scanner, timeout or malformed package is degraded execution, not a
successful scan or a malware finding. Inapplicable checks do not run. The worker's
current policy and result models define required checks; the UI displays those results.

Follow the CLI's mechanical admission decision. Do not bypass failed compatibility,
access, integrity or required-evidence checks. See [trust](trust-and-safety/index.md).
