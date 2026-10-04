---
description: "Coordinated standard-family identity, contract digest, and classification axes."
last_verified: "2026-10-04"
---

# Standard family

The field owner is `packages/contracts/src/ai_stp_contracts/standard.py` and
`schemas/v1/cli-standard-inventory.schema.json`. Requirements live in
`SPEC-060`. The architectural decision is `ADR-0154`.

`ai-stp-standard/1` is the coordinated family. It is not HTTP `/v1`, not
envelope `schema_version: 1`, not kit `protocol_version` 3, and not
`component-scaffold/6`.

`ai-stp version` and `ai-stp contract inventory` report the family and the
current contract digest. They read the generated record
`ai_stp_contracts/standard_inventory.json` rather than rendering every schema
per call; `python -m ai_stp_contracts.inventory_record --check` (run by
`just back-static` and the `package` job) refuses a record that differs from
the models. New local scaffold descriptors record
`standard_family`. Historical descriptors without that field stay historical;
readers do not fill it in.
