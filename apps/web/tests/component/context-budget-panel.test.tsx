import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

import {
  ContextBudgetPanel,
  type ContextBudgetLabels,
} from "@/components/organisms/context-budget-panel";
import type { SetupContextBudget } from "@/lib/api/catalog";
import en from "../../messages/en.json";
import ru from "../../messages/ru.json";

const labels: ContextBudgetLabels = {
  title: "Context budget",
  lead: "Potential context this setup can add, not actual model usage.",
  always: "Always loaded",
  alwaysHint: "Included every time the setup loads.",
  conditional: "Loaded when used",
  conditionalHint: "Added only when the agent uses that component.",
  total: "Potential total",
  unavailable: "Unavailable components",
  empty: "No tokenized components",
  error: "The exact setup graph cannot be measured.",
  tokens: "tokens",
  checkLocally: "Check locally",
  localCommandTitle: "Local full report",
  localCommandBody: "Run this locally",
  copy: "Copy",
  copied: "Copied",
  copyError: "Copy failed",
  docs: "Docs",
  cost: {
    title: "Cost estimate",
    rateLabel: "Input price per million tokens",
    estimate: "Estimated cost",
    empty: "Enter a rate to estimate cost. This is not actual usage.",
    invalid: "The rate must be a non-negative number.",
    hint: "Calculated only in this browser.",
  },
};

const command = "ai-stp select impact --setup-id setup_a --setup-version 1.0";

const budget: SetupContextBudget = {
  schema_version: 1,
  coordinate: { stable_id: "setup_a", version: "1.0", passport_digest: "sha256:aa" },
  estimator: {
    profile: "ai-stp:utf8-bytes/1",
    accuracy: "exact",
    method: "utf8_byte_count",
  },
  always_tokens: 1000,
  conditional_tokens: 1000,
  total_tokens: 2000,
  unavailable_components: 0,
  status: "ready",
  components: [
    {
      component: { stable_id: "component_a", version: "1.0", passport_digest: "sha256:bb" },
      component_type: "instruction",
      loading: "always",
      status: "exact",
      tokens: 1000,
      utf8_bytes: 1000,
    },
  ],
};

describe("ContextBudgetPanel", () => {
  it("keeps RU and EN distilled labels equivalent", () => {
    expect(en.catalog.contextBudgetCheckLocally).toBe("Check locally");
    expect(ru.catalog.contextBudgetCheckLocally).toBe("Проверить локально");
    expect(en.catalog.contextBudgetAlways).toBe("Always loaded");
    expect(ru.catalog.contextBudgetAlways).toBe("Всегда загружается");
    expect(en.catalog.contextBudgetConditional).toBe("Loaded when used");
    expect(ru.catalog.contextBudgetConditional).toBe("Загружается при использовании");
  });

  it("keeps the collapsed surface to title, lead and potential total", () => {
    render(<ContextBudgetPanel budget={budget} command={command} labels={labels} />);
    expect(screen.getByRole("button", { name: /Context budget/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByText(/Potential context this setup can add/)).toBeVisible();
    expect(screen.getByText(/2000 tokens/)).toBeVisible();
    expect(screen.queryByText("Always loaded")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Input price per million tokens")).not.toBeInTheDocument();
    expect(screen.queryByText(command)).not.toBeInTheDocument();
    expect(screen.queryByText("ai-stp:utf8-bytes/1")).not.toBeInTheDocument();
  });

  it("reveals the breakdown and cost only after the first disclosure", async () => {
    const user = userEvent.setup();
    render(<ContextBudgetPanel budget={budget} command={command} labels={labels} />);
    await user.click(screen.getByRole("button", { name: /Context budget/ }));
    expect(screen.getByText("Always loaded")).toBeVisible();
    expect(screen.getByText("Loaded when used")).toBeVisible();
    expect(screen.getByText("Potential total").parentElement).toHaveTextContent("2000");
    expect(screen.getByLabelText("Input price per million tokens")).toBeVisible();
    expect(screen.queryByText(command)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check locally" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("hides the local impact command until the nested disclosure opens", async () => {
    const user = userEvent.setup();
    render(<ContextBudgetPanel budget={budget} command={command} labels={labels} />);
    await user.click(screen.getByRole("button", { name: /Context budget/ }));
    await user.click(screen.getByText("Check locally"));
    expect(screen.getByText(command)).toBeVisible();
  });

  it("computes a client-only cost after the first disclosure", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    render(<ContextBudgetPanel budget={budget} command={command} labels={labels} />);
    await user.click(screen.getByRole("button", { name: /Context budget/ }));
    await user.type(screen.getByLabelText("Input price per million tokens"), "3");
    expect(screen.getByText(/Estimated cost: 0.00600000/)).toBeVisible();
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  it("shows the error on the collapsed surface when the graph is invalid", () => {
    render(
      <ContextBudgetPanel
        budget={{ ...budget, status: "invalid_graph" }}
        command={command}
        labels={labels}
      />,
    );
    expect(screen.getByText("The exact setup graph cannot be measured.")).toBeVisible();
    expect(screen.queryByText(/2000 tokens/)).not.toBeInTheDocument();
  });
});
