# Canonicalization golden corpus

Language-neutral fixtures for any future implementation of the canonicalization
layer; the Python tests in `tests/contract/` are their first consumer.

## `canonical/` — positive vectors

Each file is a JSON object with these fields:

- `name` — vector name;
- `value` — parsed input value as received, before normalization;
- `canonical` — exact RFC 8785 canonical bytes after NFC, represented as a UTF-8 string;
- `digests` — domain hashes of those bytes for each domain in `canonical-data.md`.

An implementation must produce `canonical` byte-for-byte and produce matching
hashes. The vectors cover key sorting, NFC decomposition, Cyrillic and emoji,
extreme numbers (`-0.0` → `0`, exponents, the safe integer boundary), control
character escaping, and empty containers.

## `canonical-invalid/` — negative byte corpus

Raw bytes that must produce a typed rejection from
`canonize(from_json_bytes(data))` under REQ-1504: a BOM prefix and an interior
BOM, duplicate keys before normalization, an NFC key collision, `NaN`/`Infinity`
literals, invalid UTF-8, an integer outside the `2^53` domain, and truncated JSON.
The expected reason for each file is fixed in
`tests/contract/test_canonical_bytes.py`; a rejection for another reason is an error.

The foundation code generates the vectors, and they are not rewritten after
being fixed. A change to canonicalization behavior requires new vectors and a
decision, not edits to old ones.
