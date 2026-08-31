---
description: "Shared /v1 fixture corpus: case kinds, invariants, and usage by both sides."
last_verified: "2026-08-05"
---

# Fixture corpus

The case field owners are the `ai_stp_contracts.fixtures` models; this document defines what a case is, which kinds exist, and which rules the corpus must satisfy.

There is one shared corpus. The client is tested against a mock built from these cases; the API implementation is tested against the same corpus through `ai_stp_contracts.conformance`. Two independently written example sets would agree only by chance, and the first divergence would surface as a production error rather than a failing test.

The corpus is therefore shipped **inside the package**, not in the test directory: the server track imports `ai_stp_contracts.fixtures`, and a corpus that cannot be imported is not shared.

## Case kinds

The word “negative” is insufficient: it hides which side is at fault.

| Kind | Meaning | Served by the mock | Replayed by the suite |
|---|---|---|---|
| `positive` | A request to which a conforming server responds with exactly this body. | yes | yes |
| `example` | A valid body that is **not selected by the request**: it depends on server state. | no | no |
| `rejected_request` | A request the server must reject, with a stable error code. | yes | yes |
| `invalid_response` | A body the **client** must reject. | no | no |

The `example` kind exists because some responses are selected by state rather than by the call: the same readiness probe responds with `ready` or `not_ready` depending on the deployment. Calling such a body positive would make the mock ambiguous and order-dependent.

The `invalid_response` kind has no equivalent in a request-only corpus. It proves that the client does not silently accept a broken server.

A rejection without a stable code is not allowed: two implementations could reject differently and both appear correct.

## Invariants

The corpus must satisfy all of them, and each is enforced by a check:

- no two replayable cases respond to the same request—otherwise the mock is order-dependent;
- every operation has at least one positive case;
- a case for an operation with a body sends a body, while one for an operation without a body does not;
- every passport in the corpus is sealed from its own content: a copied `revision_id` would match the template and no one would catch it;
- every rejection names a registered code whose status matches the closed registry and targets an operation that declares that code;
- case data contains ASCII only: a fixture readable as prose invites translation, and a translated fixture no longer fixes the bytes it was written to protect.

## Model and schema conformance

The invariant is difference, not equality. Some rules cannot be expressed in JSON Schema: the `authoritative` lane requires both verification markers, `ready` requires healthy checks, a public route requires a published passport, and a timestamp must denote a real instant. The model is intentionally stricter.

The reverse is unacceptable: if the model accepts a body rejected by the published schema, a schema-validating gateway will reject a payload our own code considers valid. The corpus must exercise both sides of the asymmetry, or it becomes an excuse for untested rules.

## Usage

The client side uses `ai_stp_contracts.mock`: the transport responds only from the corpus and raises an exception for an unexpected request instead of inventing a response. An invented response would teach the client behavior no one agreed upon.

The server side uses `ai_stp_contracts.conformance`: the suite accepts an `httpx` client, so mock transport, ASGI transport, and a deployment URL are indistinguishable to it. The result is a set of findings, not an exception: a suite that stopped at the first problem would hide the rest.

## Internal case consistency

A case carrying both a passport and its `passport_digest` must be internally consistent: the digest is computed from the published passport in the `ai-stp:passport:v1` domain. A placeholder instead of the real value teaches the client that integrity validation fails on correct data—and that is exactly how three corpus cases survived until the first attempt to verify the digest.
