/**
 * Canonical install-command module (SPEC-022 REQ-2204, cli-copy-templates.md).
 * Landing copies this string verbatim. Never assemble the install command in UI.
 */

import { INSTALL_CLI } from "@/lib/cli-copy";

export const INSTALL_COMMAND = INSTALL_CLI;

export const INSTALL_PREREQUISITES = ["uv", "python>=3.12"] as const;
