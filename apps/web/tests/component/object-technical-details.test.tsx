import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ObjectTechnicalDetails } from "@/components/molecules/object-technical-details";

const supportLabels = {
  tier: "Support tier",
  state: "Support state",
  evidence: "Support evidence",
  noEvidence: "none",
  result: "Result",
  observedAt: "Observed",
  expiresAt: "Expires",
  noExpiry: "no expiry",
};

describe("ObjectTechnicalDetails", () => {
  it("links a known license and embeds support evidence", async () => {
    const user = userEvent.setup();
    render(
      <ObjectTechnicalDetails
        title="Technical details"
        summary="0.1 · active"
        facts={[{ label: "Lifecycle", value: "active" }]}
        tags={["python"]}
        licenseId="MIT"
        licenseLabel="License"
        support={{
          schema_version: 1,
          tier: "beta",
          state: "verified",
          evidence: [],
        }}
        supportLabels={supportLabels}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Technical details/ }));
    expect(screen.getByRole("link", { name: "MIT" })).toHaveAttribute(
      "href",
      "https://spdx.org/licenses/MIT.html",
    );
    expect(screen.getByText("Support evidence")).toBeVisible();
    expect(screen.queryByText("View exact source")).not.toBeInTheDocument();
  });

  it("keeps an unknown license as text and shows source metadata without a GitHub link", async () => {
    const user = userEvent.setup();
    render(
      <ObjectTechnicalDetails
        title="Technical details"
        facts={[{ label: "Harness", value: "claude-code" }]}
        licenseId="CUSTOM-LICENSE"
        licenseLabel="License"
        source={{
          repository: "https://github.com/example/repo",
          commit: "b".repeat(40),
          path: "components/demo",
        }}
        sourceLabels={{
          repository: "Repository",
          commit: "Commit",
          path: "Path",
          empty: "None listed",
        }}
        supportLabels={supportLabels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Technical details/ }));
    expect(screen.queryByRole("link", { name: "CUSTOM-LICENSE" })).not.toBeInTheDocument();
    expect(screen.getByText("CUSTOM-LICENSE")).toBeVisible();
    expect(screen.getByText("https://github.com/example/repo")).toBeVisible();
    expect(screen.getByText("b".repeat(40))).toBeVisible();
    expect(screen.getByText("components/demo")).toBeVisible();
    expect(screen.queryByRole("link", { name: /View source/ })).not.toBeInTheDocument();
  });
});
