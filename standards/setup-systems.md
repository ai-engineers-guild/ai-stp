# Setup components

The seven public `NDDev-OpenNetwork/*-setup-system` repositories publish ai-stp
installation components. Their Rust sources are rendered from the private
`setup-systems` workspace. Users operate them through the
[native CLI](../apps/cli/README.md), which authenticates releases and invokes
components; only a component writes the final harness configuration.

Current owners:

- `apps/cli/src/provider/managed.rs`: default exact component release;
- `apps/cli/src/provider/artifact/`: artifact identity and publisher policy;
- `apps/cli/src/provider/trust/`: signed metadata and rollback protection;
- `apps/cli/src/provider/runtime/`: confined execution and durable recovery;
- `release_scripts/provider_kit.py`: generated `provider-kit/v3`;
- `tests/golden/provider-kit/identity-ledger.json`: immutable released kit digests.

Never edit rendered public trees or generated kits by hand. Release compatible
readers before components that require new fields. Retained operations keep their
original exact version; a downloaded manifest cannot widen local publisher policy.
Harness executables themselves remain entirely user/vendor managed.

Native provider execution and handoff are currently Linux-only. Other operating
systems explicitly refuse unsupported isolation. Use `capabilities` and the native
README for platform boundaries. Test fixtures use disposable homes and targets.

`just back-static` checks kit drift. `just cli-check` proves the native boundary.
Per-release component journeys and measured platform evidence live in GitHub,
attached to their exact source/tag, rather than in a copied status journal.
