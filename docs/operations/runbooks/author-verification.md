---
description: "Staff authorization and the meaning of author verification."
last_verified: "2026-10-15"
---

# Author verification

`POST /v1/staff/author-verified` grants or revokes the author attribute. Staff access
is limited by `AI_STP_AUTH_ADMIN_ACCOUNT_IDS` in the host environment. An empty value
authorizes nobody, including the operator. Changing that list expands access and
requires the corresponding task authority.

Verify the author's account or namespace ownership and record the granting actor,
rationale and time through the staff operation. Read back the resulting attribute.
Author verification establishes provenance; it does not certify artifact safety
or grant `component_verified`. Revocation changes future trust decisions without
rewriting immutable versions or installed targets.
