---
description: "Closed event fields and redaction at the API and worker log sinks."
last_verified: "2026-09-07"
---

# Structured logging

`ai_stp_platform.logging` owns the closed optional-field registry in
`_ALLOWED_FIELDS`. It admits event identity, request/trace correlation,
object/job coordinates, closed state labels and numeric operational metrics.
Unknown fields and nested objects are removed before either sink receives them.
An exception contributes its class, never its message, traceback or local values.
Known credential markers, URLs and email addresses in admitted strings are
redacted; event names are bounded machine identifiers.

Both sinks receive the same JSON event: stdout and `ai_stp.log`, rotated at UTC
midnight with fourteen daily backups. Reconfiguration removes and closes the
previous platform-owned handlers before installing the new pair. Third-party
standard-library records become `external_log` with logger, level and optional
exception class; their arbitrary message and arguments do not become a payload.
The API entry point disables Uvicorn's separate access log and logging configuration
so raw callback URLs, client addresses and query strings do not bypass this sink.
The implementation uses structlog's
[standard-library formatter boundary](https://www.structlog.org/en/stable/standard-library.html).

Call sites must pass only non-sensitive scalar metadata even when the key is
admitted. This sink is defense in depth, not permission to put secrets in a
`reason` or identifier. Privacy requirements belong to SPEC-013; rotation and
correlation requirements belong to SPEC-017 and ADR-0039.
