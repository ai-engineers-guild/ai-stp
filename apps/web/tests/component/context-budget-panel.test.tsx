import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  ComponentContextBudgetPanel,
  ContextBudgetPanel,
  type ContextBudgetLabels,
} from "@/components/organisms/context-budget-panel";
import type { ComponentContextBudget, SetupContextBudget } from "@/lib/api/catalog";

const labels = {
  title: "Context budget",
  lead: "Potential context",
  runtimeDerived: "Runtime schemas are not available.",
  always: "Always loaded",
  alwaysHint: "Always",
  conditional: "Loaded when used",
  conditionalHint: "When used",
  total: "Potential total",
  unavailable: "Unavailable components",
  empty: "Empty",
  error: "Cannot estimate",
  tokens: "tokens",
  checkLocally: "Check locally",
  localCommandTitle: "Local report",
  localCommandBody: "Run locally",
  copy: "Copy",
  copied: "Copied",
  copyError: "Copy failed",
  docs: "Docs",
  cost: {
    title: "Cost",
    rateLabel: "Rate",
    estimate: "Estimate",
    empty: "Empty",
    invalid: "Invalid",
    hint: "Hint",
  },
} satisfies ContextBudgetLabels;

const estimator = {
  profile: "ai-stp:unicode-chars-div4/1" as const,
  accuracy: "estimated" as const,
  method: "unicode_codepoints_div_4" as const,
};

const setupBudget: SetupContextBudget = {
  schema_version: 1,
  coordinate: { stable_id: "setup_a", version: "1.0", passport_digest: "sha256:aa" },
  estimator,
  always_tokens: 250,
  conditional_tokens: 750,
  total_tokens: 1000,
  unavailable_components: 0,
  status: "ready",
  components: [],
};

describe("ContextBudgetPanel", () => {
  it("shows only potential total and loaded-when-used estimates", async () => {
    const user = userEvent.setup();
    render(<ContextBudgetPanel budget={setupBudget} labels={labels} />);
    expect(screen.getByText(/1,?000 tokens/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Context budget/ }));
    expect(screen.getByText("Potential total").parentElement).toHaveTextContent(/1[\s,]?000/);
    expect(screen.getByText("Loaded when used").parentElement).toHaveTextContent("750");
    expect(screen.queryByText("Always loaded")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("shows the explicit unavailable state", () => {
    render(<ContextBudgetPanel budget={null} labels={labels} />);
    expect(screen.getByText("Cannot estimate")).toBeVisible();
  });
});

describe("ComponentContextBudgetPanel", () => {
  it("shows the two estimates for a conditional component", async () => {
    const user = userEvent.setup();
    const budget: ComponentContextBudget = {
      schema_version: 1,
      coordinate: { stable_id: "component_a", version: "1.0", passport_digest: "sha256:aa" },
      estimator,
      component_type: "skill",
      loading: "conditional",
      tokens: 640,
      utf8_bytes: 2560,
      status: "estimated",
      reason: null,
    };
    render(<ComponentContextBudgetPanel budget={budget} labels={labels} />);
    await user.click(screen.getByRole("button", { name: /Context budget/ }));
    expect(screen.getByText("Potential total").parentElement).toHaveTextContent("640");
    expect(screen.getByText("Loaded when used").parentElement).toHaveTextContent("640");
  });

  it("does not pretend package bytes are MCP schema tokens", () => {
    render(
      <ComponentContextBudgetPanel
        budget={{
          schema_version: 1,
          coordinate: {
            stable_id: "component_mcp",
            version: "1.0",
            passport_digest: "sha256:bb",
          },
          estimator,
          component_type: "mcp",
          loading: null,
          tokens: null,
          utf8_bytes: null,
          status: "not_applicable",
          reason: "runtime_context_not_statically_measurable",
        }}
        labels={labels}
      />,
    );
    expect(screen.getByText("Runtime schemas are not available.")).toBeVisible();
  });
});
