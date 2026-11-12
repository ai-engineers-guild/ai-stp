#!/usr/bin/env bash
# Verify the one packaged macOS disk image.
set -euo pipefail
images=(apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg)
test "${#images[@]}" -eq 1 && test -f "${images[0]}"
/usr/bin/hdiutil verify "${images[0]}"
