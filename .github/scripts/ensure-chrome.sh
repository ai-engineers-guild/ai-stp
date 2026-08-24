#!/usr/bin/env bash
# Make sure a Google Chrome the Playwright config can drive is present.
#
# `playwright.config.ts` sets `channel: "chrome"`, so the suite drives the
# stable Chrome installed on the machine and never the Playwright-managed
# chromium. Both callers used to download a browser anyway: the gate fetched
# Chrome again on every run — fifty-nine seconds on its longest job — and the
# local recipes fetched chromium, which the config does not use at all.
#
# Every current runner image ships Chrome (measured on ubuntu-24.04,
# windows-2022 and macos-15), and so does a normal developer machine. The
# download is the fallback for when that stops being true, not the default.
set -euo pipefail

for candidate in \
  "$(command -v google-chrome || true)" \
  "$(command -v google-chrome-stable || true)" \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"; do
  if [ -n "${candidate}" ] && [ -x "${candidate}" ]; then
    echo "ensure-chrome: using ${candidate}"
    exit 0
  fi
done

echo "ensure-chrome: no Chrome on this machine; installing one" >&2
cd "$(dirname "$0")/../../apps/web"
bun x playwright install chrome
