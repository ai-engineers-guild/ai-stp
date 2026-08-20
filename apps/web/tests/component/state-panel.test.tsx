import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatePanel } from "@/components/molecules/state-panel";

/**
 * REQ-2202: loading / error / empty states exist as components.
 * REQ-2213: each of them is announced to assistive technology, and the urgency
 * matches the state — an error interrupts, a background load does not.
 */
describe("StatePanel", () => {
  it("announces an error assertively through the alert role", () => {
    render(<StatePanel kind="error" title="API unavailable" description="try again" />);

    const panel = screen.getByRole("alert");
    expect(panel).toHaveAttribute("aria-live", "assertive");
    expect(screen.getByText("API unavailable")).toBeInTheDocument();
    expect(screen.getByText("try again")).toBeInTheDocument();
  });

  it("announces an empty result as status, not as an error", () => {
    render(<StatePanel kind="empty" title="Nothing found" />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    // An empty catalog is a normal outcome: it must not reach AT as an alert.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("announces loading politely so it does not interrupt", () => {
    render(<StatePanel kind="loading" title="Loading" />);

    const panel = screen.getByRole("status");
    expect(panel).toHaveAttribute("aria-live", "polite");
  });

  it("omits description and action when not supplied", () => {
    render(<StatePanel kind="empty" title="Only a title" />);

    const panel = screen.getByRole("status");
    // kind mono label + title; description and action stay optional
    expect(panel.querySelectorAll("p")).toHaveLength(2);
    expect(screen.getByText("empty")).toBeInTheDocument();
    expect(screen.getByText("Only a title")).toBeInTheDocument();
    expect(panel.querySelector("div.mt-4")).toBeNull();
  });

  it("renders a recovery action when one is supplied", () => {
    render(
      <StatePanel kind="error" title="Failed" action={<button type="button">Retry</button>} />,
    );

    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
