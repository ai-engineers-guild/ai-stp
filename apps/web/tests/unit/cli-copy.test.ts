import { describe, expect, it } from "vitest";
import {
  CLI_RELEASES_URL,
  installSetupStart,
  installTaskStart,
  login,
  registryVersion,
} from "@/lib/cli-copy";

describe("native CLI handoffs", () => {
  it("preserves exact object pins in commands and agent prompts", () => {
    const id = "setup_01KZWSHE3V0T8KVJYFEKWJV63Z";
    expect(registryVersion("setup", id, "2.13")).toBe(
      `ai-stp registry version --kind setup --id ${id} --version 2.13`,
    );
    expect(installSetupStart(id, "2.13")).toContain(`${id} version 2.13`);
    expect(installSetupStart(id, "2.13")).toContain("ai-stp task intents --json");
    expect(installSetupStart(id, "2.13")).not.toContain("--input -");
    expect(() => installTaskStart("bad id")).toThrow();
  });
  it("uses native archives and provider-specific account plans", () => {
    expect(CLI_RELEASES_URL).toBe(
      "https://github.com/ai-engineers-guild/ai-stp/releases/tag/cli-v0.1.2",
    );
    expect(login("github")).toBe("ai-stp account plan --action start --provider github --json");
    expect(login("google")).toContain("--provider google");
  });
});
