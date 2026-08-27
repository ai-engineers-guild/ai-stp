# mcp fixture

The correct way to need a credential: declare the variable, carry no value.

`required_env` names `VENDOR_CREDENTIAL` and `GITHUB_TOKEN` and holds neither of
them. `mcp_secret_like` looks for a credential keyword next to a separator and
a long value, and both names sit next to a comma instead — which is the whole
difference between declaring a variable and leaking one.

If this tripped the rule, every correctly authored MCP component would carry a
high finding and the rule would be ignored within a week. That is what this
case measures: the corpus's own headline number is the benign false-positive
rate.

The matching malicious case — the same two variable names with real values, in
the JSON shape an MCP configuration is actually written in — lives in
`tests/unit/platform/test_safety_cli_adapters.py`. It is not here because the
corpus holds each kind to at most twenty malicious cases and `mcp` is at
twenty; a balance guard is not something to move so that new work fits.
