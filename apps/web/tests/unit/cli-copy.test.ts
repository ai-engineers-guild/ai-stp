import { describe, expect, it } from "vitest";

import {
  DISTRIBUTION,
  INSTALL_CLI,
  login,
  ownerComponentNextStep,
  ownerSetupNextStep,
  registryCommand,
  registryShow,
  registryVersion,
  selectImpact,
} from "@/lib/cli-copy";
import { INSTALL_COMMAND } from "@/lib/install/install-command";

const SAMPLE_COMPONENT = "component_01KZWSHE3V0T8KVJYFEKWJV63Y";
const SAMPLE_SETUP = "setup_01KZWSHE3V0T8KVJYFEKWJV63Z";

describe("cli-copy templates", () => {
  it("renders the canonical registry commands", () => {
    expect(registryShow("component", SAMPLE_COMPONENT)).toBe(
      `ai-stp registry show --kind component --id ${SAMPLE_COMPONENT}`,
    );
    expect(registryVersion("setup", SAMPLE_SETUP, "1.0")).toBe(
      `ai-stp registry version --kind setup --id ${SAMPLE_SETUP} --version 1.0`,
    );
    expect(registryCommand(SAMPLE_COMPONENT, "2.13")).toBe(
      `ai-stp registry version --kind component --id ${SAMPLE_COMPONENT} --version 2.13`,
    );
    expect(selectImpact(SAMPLE_SETUP, "1.0")).toBe(
      `ai-stp select impact --setup-id ${SAMPLE_SETUP} --setup-version 1.0`,
    );
  });

  it("renders owner next steps and login without paths or secrets", () => {
    expect(ownerComponentNextStep()).toBe("ai-stp component discover");
    expect(ownerSetupNextStep()).toBe("ai-stp toolchain harnesses");
    expect(login("github")).toBe("ai-stp auth login --provider github");
    expect(login("google")).toBe("ai-stp auth login --provider google");
  });

  it("installs the published distribution name", () => {
    expect(INSTALL_COMMAND).toBe(INSTALL_CLI);
    expect(DISTRIBUTION).toBe("ai-stp-cli");
    expect(INSTALL_CLI).toBe("uv tool install ai-stp-cli");
    for (const sample of [
      registryCommand(SAMPLE_COMPONENT, "2.0"),
      ownerComponentNextStep(),
      ownerSetupNextStep(),
      login("github"),
      INSTALL_CLI,
    ]) {
      expect(sample.includes("ai-stp use ")).toBe(false);
      expect(sample.includes("@")).toBe(false);
    }
  });
});
