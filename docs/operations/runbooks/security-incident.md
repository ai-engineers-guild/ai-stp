---
description: "Contain an affected published version and preserve recovery evidence."
last_verified: "2026-11-03"
---

# Security incident

1. Identify the exact affected version, source commit, artifact digest and known
   installations. Report privately through [the security policy](../../../SECURITY.md).
2. Block the affected catalog version and stop further distribution/selection
   through the owning publication service. Preserve immutable source, artifacts,
   original plans and operation outcomes for investigation and recovery.
3. Revoke compromised device credentials or publisher access through their owning
   account/service. Inspect pending operations; an unknown outcome is not a
   successful cancellation or rollback.
4. Qualify and publish a corrected new version through the normal client release
   checks. Verify actual served bytes and affected native application journeys.
5. Notify affected users through a secure channel and add a regression covering
   the observed failure. Keep secrets and exploitation details out of public logs.
