---
description: "Runbook: best-effort GitHub stars cache for the public catalog."
last_verified: "2026-09-03"
---

# GitHub repository metrics

The worker updates `github_stars` from the canonical public provenance repository
after publication. A successful value is considered fresh for 12 hours; errors preserve
the previous value and use bounded backoff up to 24 hours. An unavailable
or private repository is not shown as zero, and the metric does not affect trust.

For a higher rate limit, `AI_STP_WORKER_GITHUB_TOKEN` is set. The same token
is used by Official upstream git resolution. The fine-grained token must have
only public metadata access; write permissions and access to private
repositories are not required. The token value is not written to the
database, logs, API responses, or fixtures.
