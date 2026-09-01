import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  mergeRequirements,
  RequirementsSummary,
} from "@/components/molecules/requirements-summary";

const labels = {
  title: "Requirements",
  credentials: "Credentials",
  authorization: "Authorization",
  environment: "Environment",
  permissions: "Permissions",
  endpoints: "Endpoints",
  components: "Components",
  capabilities: "Capabilities",
  harnessVersions: "Harness versions",
  operatingSystems: "Operating systems",
  architectures: "Architectures",
  harnesses: "Harnesses",
  runtime: "Runtime",
  none: "None",
  yes: "Yes",
  no: "No",
};
describe("RequirementsSummary", () => {
  it("aggregates setup and pinned component declarations", () => {
    const merged = mergeRequirements([
      {
        required_env: [],
        requires_credentials: false,
        requires_authorization: "none",
        permissions: { filesystem: [], network: [], process: [] },
        external_endpoints: [],
      },
      {
        required_env: [{ name: "SERVICE_TOKEN", purpose: "Authenticate requests" }],
        requires_credentials: true,
        requires_authorization: "external_service",
        permissions: { filesystem: ["read:config"], network: [], process: [] },
        external_endpoints: ["https://api.example.test/v1"],
        requires_components: [
          {
            stable_id: "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            version: "1.0",
            passport_digest:
              "sha256:0000000000000000000000000000000000000000000000000000000000000000",
          },
        ],
        requires_capabilities: ["project.language.python"],
      },
    ]);
    expect(merged.requires_credentials).toBe(true);
    expect(merged.required_env).toHaveLength(1);
    expect(merged.permissions.filesystem).toEqual(["read:config"]);
    expect(merged.requires_components).toHaveLength(1);
    expect(merged.requires_capabilities).toEqual(["project.language.python"]);
  });

  it("renders declarations without inventing secret values", () => {
    render(
      <RequirementsSummary
        requirements={{
          required_env: [{ name: "SERVICE_TOKEN", purpose: "Authenticate requests" }],
          requires_credentials: true,
          requires_authorization: "external_service",
          permissions: { filesystem: ["read:config"], network: ["api.example.test"] },
          external_endpoints: ["https://api.example.test/v1"],
          requires_capabilities: ["project.language.python"],
          supported_harness_versions: [">=2.1"],
          supported_os: ["linux"],
          supported_arch: ["x86_64"],
        }}
        labels={labels}
      />,
    );
    fireEvent.click(screen.getByText(labels.title));
    expect(screen.getByText("SERVICE_TOKEN — Authenticate requests")).toBeVisible();
    expect(screen.getByText("filesystem: read:config")).toBeVisible();
    expect(screen.getByText("https://api.example.test/v1")).toBeVisible();
    expect(screen.getByText("project.language.python")).toBeVisible();
    expect(screen.getByText(">=2.1")).toBeVisible();
    expect(screen.getByText("linux")).toBeVisible();
  });

  it("keeps empty requirement groups visible", () => {
    render(
      <RequirementsSummary
        requirements={{
          required_env: [],
          requires_credentials: false,
          requires_authorization: "none",
          permissions: { filesystem: [], network: [], process: [] },
          external_endpoints: [],
        }}
        labels={labels}
      />,
    );
    fireEvent.click(screen.getByText(labels.title));
    expect(screen.getByText(labels.credentials)).toBeVisible();
    expect(screen.getByText(labels.authorization)).toBeVisible();
    expect(screen.getByText(labels.environment)).toBeVisible();
    expect(screen.getByText(labels.permissions)).toBeVisible();
    expect(screen.getAllByText(labels.none).length).toBeGreaterThan(0);
  });
});
