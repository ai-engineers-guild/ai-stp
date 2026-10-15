---
title: "Overview"
description: "Current Rust CLI, account and catalog guidance."
---

# ai-stp

ai-stp creates, validates, selects and installs complete configurations for AI
harnesses. The Rust CLI is the engine; the web provides accounts and the public
catalog. A setup belongs to one harness and pins exact immutable component versions.

[Install](quickstart/human.md), then let your agent use the
[task interface](quickstart/agent.md). The [CLI reference](cli/index.md) explains
command discovery and state. [Catalog](catalog/index.md) and
[trust](trust-and-safety/index.md) explain what public results mean.

Linux x86-64, Apple Silicon macOS and Windows x86-64 run in CI. Isolated setup
installation and active-session handoff are currently available on Linux.
Harness executables remain managed by users/vendors. No model key is needed,
and the CLI has no telemetry sender or automatic updater.
