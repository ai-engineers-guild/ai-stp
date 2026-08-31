---
description: "Decision to derive authorization readiness from the exact SetupVersion and the observed status of the provider target."
last_verified: "2026-08-09"
---

# ADR-0052: Observable Readiness of External Authorization

Status: accepted.

## Context

`SPEC-008` REQ-819 and REQ-820 require declaring the need for authorization before installation and retaining `needs_configuration` until the user has completed setup. The exact `SetupVersionPassport` already aggregates `requires_authorization`, but target readiness used only a manually supplied parameter and did not read this field. Therefore, an ordinary `target status` could call a setup installed even though the setup itself declares incomplete external authorization.

The CLI cannot prove sign-in by the presence of an environment variable, a local "ready" flag, or by reading secrets. The provider exclusively owns the native target under REQ-803 and is the only layer that can safely observe whether setup of the harness it owns has been completed. At the same time, protocol v1 is frozen, and older providers do not return such evidence.

## Alternatives

1. Retain a local user marker. It outlives revocation, target changes, and deletion of the native session, and therefore can declare readiness that no longer exists.
2. Always consider declared authorization incomplete. This is safe, but the state can never become `installed` even after successful setup.
3. Make the field mandatory for protocol v1. This breaks the already released provider contract.
4. Leave the requirement with the owner of the exact passport, while obtaining readiness as optional additive evidence from `status`; treat the absence of evidence as incompleteness.

## Decision

Alternative 4 is accepted.

The exact selected `SetupVersionPassport` is the sole source of the required kind:

```text
none | user_account | external_service
```

Provider `status` may additionally return:

```json
{
  "authorization": {
    "kind": "external_service",
    "state": "pending"
  }
}
```

The closed set of states is `pending` and `ready`. The field contains no token, sign-in address, account name, or other secret. Its absence remains a valid response from an older provider, but for a setup with a requirement it means `pending`, not readiness.

The consumer acts fail closed:

- `requires_authorization: none` and the absence of evidence mean that there is no requirement;
- a declared requirement without provider evidence remains in `needs_configuration`;
- only an exact match of `kind` and `state: ready` clears the pending requirement;
- `state: pending` preserves the pending requirement;
- an unknown shape, unknown state, or mismatched `kind` returns a typed provider schema error and is not called ready;
- `target status` without a provider call cannot confirm completion and remains pending.

`install plan` displays `required_authorization` so that the agent can explain the requirement before applying. Installation and provider verification may complete independently: readiness is a subsequent observation, not a reason to rewrite the truthful result of the effect.

The field is an optional command-specific extension of the open JSON response and does not change the mandatory shape of protocol v1. Adding a mandatory field, a new kind, or a different meaning will require the next protocol version. Provider repositories add evidence after updating the consumer contract; older releases continue to work but cannot confirm authorization readiness.

## Consequences

- readiness can no longer be made falsely positive by omitting a CLI flag;
- revocation or loss of native authorization is observed by the next `status`, rather than conflicting with a long-lived local marker;
- the provider neither receives secrets nor reports them back;
- actual closure of REQ-820 requires E2E testing of each primary provider with the transition `pending → ready → pending` after revocation;
- the absence of the provider executable is honest incomplete evidence, not grounds for considering the target ready.

## Reconsideration Conditions

The decision will be reconsidered if a single SetupVersion must declare multiple independently completable authorizations. In that case, the single enum will be replaced with a versioned list of requirements in the passport and a new compatible status contract, rather than a free-text string.
