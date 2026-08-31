---
description: "Decision to use Click directly instead of Typer and build the parser from the command registry."
last_verified: "2026-08-29"
---

# ADR-0057: Click Directly as the CLI Command Parser

Status: accepted.

Supersedes `ADR-0013-cli-framework.md` under its own review condition.

## Context

`ADR-0013` selected Typer because type annotations on command functions eliminate
boilerplate for approximately seventeen groups. That reasoning relied on the
assumption that commands are declared as functions.

Issue #72 removed that assumption. Machine-readable help must be built from the
actual command registry, and the canonical Skill must not guess flags. Both
requirements are met only when a command has exactly one declaration and the
parser is built from it. Therefore, the registry in
`apps/cli/src/ai_stp_cli/registry.py` declares descriptors as data, and the
parser is assembled from them programmatically. There are no functions with
type annotations from which Typer could derive parameters—the sole reason for
which it was selected turned out to be inapplicable.

Testing in the real environment then yielded three measured facts:

1. Typer 0.27.1 requires Rich. It entered the dependency tree transitively, even
   though `#72` requires minimal plain text, and it would have to be suppressed
   on two separate output paths. `ADR-0013` estimated Typer's cost as “two
   transitive dependencies”; in fact, there are four, including a rendering
   library that emits escape sequences.
2. Typer 0.27.1 ships its own vendored compatibility layer for Click. Its
   `Context` does not have the `_param_default_explicit` attribute that the
   installed Click 8.4.2 reads in `Parameter.handle_parse_result`. A regular
   `click.Option` placed in a Typer group fails with `AttributeError`. Pure
   Typer works, pure Click works, and only the mixture breaks—and a parser
   generated from data is exactly such a mixture.
3. None of the Typer entry points that such a parser would require
   (`typer.main.get_group`, `typer.core.TyperOption`) are part of its public
   contract.

The review condition in `ADR-0013` is phrased as “if it begins to impose output
behavior incompatible with the strict envelope.” Item 1 satisfies it literally,
while items 2 and 3 show that working around it is possible only by relying on
library internals.

## Alternatives

1. Keep Typer and declare commands as functions, while keeping descriptors in a
   table alongside them. This restores Typer's purpose but creates two
   declarations for a single command: parameters in the signature and metadata
   (`mutability`, `confirmation`, `result_schema`, `next_actions`) in the table.
   Divergence becomes possible and is caught by a test rather than prevented by
   construction.
2. Keep Typer and build the parser from its internal classes
   (`TyperOption`, `TyperGroup`). This preserves a single declaration but relies
   on a non-public contract and does not eliminate Rich.
3. Use Click directly. The parser is still built from the registry, the single
   declaration is preserved, Rich and the vendored shim are removed, and the
   entire API used is public.
4. `argparse`. This also removes Click, but `ADR-0013` already rejected it, and
   none of the new facts changed that.

## Decision

Click is used directly. The command registry remains the sole declaration:
`app.py` assembles a `click.Group` from it, while `help --agent` renders the same
descriptors. They cannot diverge because there is only one source.

Typer is removed from the `apps/cli` dependencies. Rich and shellingham leave
the dependency tree along with it.

Click remains a constrained application layer: it parses arguments and invokes
the scenario, but it does not construct the JSON envelope, define error codes,
or select the exit code. The group runs with `standalone_mode=False`, so Click
raises an exception instead of performing its own printing and exit, while our
code selects the visible result.

Alternative 1 is rejected on substance rather than cost: “cannot diverge by
construction” is stronger than “divergence is caught by a test.”

## Consequences

- metadata not provided by Click (`mutability`, `confirmation`,
  `result_schema`, `next_actions`) lives in the descriptor and does not require
  a second storage location;
- no rendering library is included in the CLI dependency tree, so the ban on
  escape sequences in machine-readable stdout is enforced by the dependency
  set rather than by configuration;
- command path depth was limited to two levels—the forms declared by the
  registry at the time of the decision. The review condition below was met in
  #74 (`passport developer init`), the build became recursive, and the contract
  boundary remained the effective boundary: `CommandPath` permits no more than
  four segments, and a deeper declaration is rejected during the build rather
  than silently lost;
- `ADR-0013` receives superseded status and links here;
- the parser conclusion in `tech-stack.md` is updated to Click.

## Review Conditions

The path-depth condition was met in #74 and is closed: the build is recursive,
and the boundary is the four segments from `CommandPath`. The rest of the
decision is to be reviewed if Click is no longer maintained or if a parser
appears that derives parameters from data rather than from annotations.
