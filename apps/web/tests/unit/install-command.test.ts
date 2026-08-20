import { describe, expect, it } from "vitest";

import { INSTALL_CLI } from "@/lib/cli-copy";
import { INSTALL_COMMAND } from "@/lib/install/install-command";

describe("install command module (REQ-2204)", () => {
  it("exports the canonical install template", () => {
    expect(INSTALL_COMMAND).toBe(INSTALL_CLI);
    expect(INSTALL_COMMAND).toBe("uv tool install ai-stp-cli");
  });
});
