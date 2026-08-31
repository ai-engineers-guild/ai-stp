---
description: "Access grant target, recipient actions, forks, derivative publication, and revocation consequences."
last_verified: "2026-08-04"
---

# Access grants, forks, and derivative publication

The requirements owners are `SPEC-002` for grants and `SPEC-005` for forks and publication; the decision is `ADR-0030`, and the invitation transport is `ADR-0020`. This document defines the machine boundary: what a grant addresses, what it permits, and what happens upon forking, derivative publication, and revocation.

## Grant target

```json
{
  "object_id": "setup_...",
  "major": 1
}
```

A grant addresses an exact object and one of its major lines. A grant for version `X.Y` applies to the entire `X.*` line: the recipient can see existing and future minor versions within `X`. The new major line `X+1` is not covered and requires a new grant from the owner.

A direct grant may address the recipient through `github_username`. This is a
separate discriminated type, not a string heuristic: the value is normalized to
lowercase without a leading `@`, resolved through an active linked GitHub
identity, and the grant then stores the stable `grantee_account_id`. The original
type and normalized value are retained only to explain the grant; a later username
rename does not change an already issued grant.

The alternative `user_id` type accepts only a canonical stable account ID. It is
not normalized or interpreted as a GitHub username or email. After confirming
that the account exists, the grant uses the same ID as `grantee_account_id`; an
unknown or inaccessible value reveals no account state beyond a uniform
`not found`.

## Recipient actions

| Action | Permitted by the grant |
|---|---|
| read metadata and bytes of line versions | yes |
| install line versions | yes |
| fork into one's own private object | yes |
| edit the original | no, owner only |
| grant access onward to a third party | no, owner only |

A recipient's write to another person's object is rejected at the authorization layer; knowing an object identifier does not create a grant under `SPEC-002`.

## Fork

A fork creates a new private object owned by the recipient **of the same kind**: a setup remains a setup and a component remains a component; the kind does not change when forked:

- a new stable identifier; the original identifier is not reused;
- the recipient is the owner; the default mode is private;
- provenance is recorded as a reference to the source object and version;
- the fork may be synchronized to the recipient's private cloud registry.

The constrained component overlay with `derived_from` under `component-setup-passports.md` remains a separate mechanism for small changes and is not replaced by a fork.

A fork does not change the original or expand the grant: access to future versions of the original is determined by the grant, not by the existence of a fork.

## Derivative publication

An unchanged clone of another person's object is not published under a new namespace. Publishing a derivative:

- a setup requires a substantive change to its composition, passport, or included component bytes and full validation under `validation-policy.md`;
- a component requires changed bytes or passport and a new identity and version in the recipient's namespace;
- public publication is allowed only when every included byte and reference is public or owned by the recipient and applicable licenses permit distribution;
- another party's private bytes are not published unchanged; unknown distribution rights fail closed.

The derivative object's provenance retains a reference to the source under the passport rules.

## Revocation

Grant revocation applies prospectively:

- future cloud reads and retrieval of minor versions in the line stop;
- bytes already retrieved, local forks, and installed targets are not deleted;
- a rebuild that needs an inaccessible private dependency ends with a precise typed access error naming the inaccessible object, rather than silent substitution or degradation.

Revoking an invitation and revoking an issued grant remain separate actions under `SPEC-002`.
