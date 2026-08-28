# Surfaces

Report what this harness owns, what it declines, and what decided each row.

Ask the binary directly:

```bash
codex-setup-system provider-info
```

and compare it against `references/<harness>-baseline.json`. The two are bound
by a test; if they disagree in a checkout, the test is the thing to run.

Report each owned path, the kinds it routes, and — for anything that routes no
kind — the reason it is owned anyway.
