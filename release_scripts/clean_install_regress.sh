#!/usr/bin/env bash
# Install the exact server/shared wheels outside the checkout.
set -euo pipefail

dist="$PWD/dist"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
uv venv "$work/venv" -q
uv pip install --python "$work/venv" -q "$dist"/*.whl
if [ -d "$work/venv/Scripts" ]; then
    interpreter="$work/venv/Scripts/python.exe"
else
    interpreter="$work/venv/bin/python"
fi
cd "$work"
"$interpreter" -I - <<'PY'
import importlib
import importlib.util
for name in ("api", "worker", "platform", "foundation", "passports", "assurance", "contracts", "sources"):
    importlib.import_module("ai_stp_" + name)
assert importlib.util.find_spec("ai_stp_cli") is None, "server wheels must not carry the retired CLI"
for name in ("openai", "anthropic", "cohere", "mistralai", "litellm", "ollama", "langchain", "transformers"):
    assert importlib.util.find_spec(name) is None, f"unexpected model client: {name}"
PY
echo 'clean_install_regress: server wheels install without a Python CLI or model client'
