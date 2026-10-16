import { expect, it } from "vitest";
import { CLI_RELEASES_URL } from "@/lib/install/install-command";
it("links to the native distribution", () => {
  expect(CLI_RELEASES_URL).toBe(
    "https://github.com/ai-engineers-guild/ai-stp/releases/tag/cli-v0.1.2",
  );
});
