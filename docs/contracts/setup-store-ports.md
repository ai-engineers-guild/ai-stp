---
description: "Contract for local discovery, preview, and component import from SX and APM."
last_verified: "2026-08-13"
---

# Local setup-store ports

## Commands

`registry port discover --root <path>` finds supported manifests.
`registry port inspect --adapter sx|apm --root <path>` displays the conversion
report. `registry port plan` adds the exact digest and operation consequences.
`registry port import` requires the same root/adapter, `--expected-plan-digest`, and
`--confirm`; its only effect is a local registry write.

Flags and result schemas belong to generated `help --agent`, so they are not duplicated
here. The external store and harness target remain byte-identical. The port does not
invoke a vendor CLI, package manager, Git, or the network.

## Shared model

The descriptor records `setup-store-port/1`, the adapter, contract version read,
manifest, domain-separated snapshot digest, and presence of the optional vendor CLI.
Each mapping entry preserves external identity/type/version, source coordinate,
available source digest, canonical component type, local path, omissions, and bounded
metadata. Unknown fields are listed as JSON-path-like pointers; they do not affect the
passport implicitly.
For an available local path, inspection additionally builds a content digest under the
same bounded rules that the subsequent import uses to read the artifact. The plan
therefore changes not only with the manifest but also when the actual bytes change.

The plan contains the entire inspection, conflicts, and five explicit trust consequences:
the object remains local-only, both verified axes are false, and the external store and
target remain unchanged. An external identity collision fails apply closed. Re-importing
the same adapter/snapshot/external identity returns the previously created stable and
revision identifiers.

## SX schema 2

The structure source is the pinned
[manifest spec](https://github.com/sleuth-io/sx/blob/a74798be061fb125b0748f083f0418e058978a13/docs/manifest-spec.md).
The port accepts only a local `source-path` that remains within the root. `source-http`
and `source-git` are shown with their coordinate/digest, but offline import does not
download them. `rule` becomes `instruction`, while `claude-code-plugin` and `app-plugin`
become `plugin`; the other six shared names match. A collection is retained in the
report as an omission: one member name is not an exact Component version/digest, so it
cannot honestly produce a Setup passport.

## APM lock 1/2

The structure source is the pinned
[lockfile implementation](https://github.com/microsoft/apm/blob/3aa0365540e3d9ef4685740cea6a09094ff35377/src/apm_cli/deps/lockfile.py).
The port groups only declared `deployed_files` by the known `skills`, `agents`,
`prompts`/`commands`, `hooks`, `plugins`, `instructions`/`rules`, and `mcp` boundaries.
`prompt` maps to canonical `command`. An unrecognized deployed path creates no component;
package type alone is not used to guess content.

## Limits and failure

A manifest is one regular non-linked UTF-8 file no larger than 4 MiB; at most 1000
records and 100 displayed unknown-field pointers are allowed; when a limit is exceeded,
the report explicitly shows the original and displayed counts. YAML duplicate keys are
prohibited. The root cannot be home, and a relative source cannot be absolute, contain
`..`, or escape the root after path resolution. An incompatible schema receives a
distinct failure, while the absence of a vendor CLI does not prevent offline
inspection/import.
