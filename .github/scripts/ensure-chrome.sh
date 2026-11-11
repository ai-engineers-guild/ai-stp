#!/usr/bin/env bash
# Exercise the selected provider-owned browser; a check never installs one.
set -euo pipefail
cd "$(dirname "$0")/../../apps/web"
exec bun scripts/ensure-chrome.mjs
