// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import NativeInventory from "./components/NativeInventory";
import type { ContextView } from "./contexts";
import * as transport from "./transport";
vi.mock("./transport", () => ({
  cmdRunRead: vi.fn(),
  cliPlan: vi.fn(),
  cliApplyConfirmed: vi.fn(),
  cmdNativeInventoryEnable: vi.fn(),
}));
const ok = (data: Record<string, unknown>) => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
const a: ContextView = {
  id: "context_original",
  label: "Original company",
  mode: "corporate",
  organization: "Company",
  origin: "https://example.test",
  connection: "connection_original",
};
const b: ContextView = { ...a, id: "context_other", label: "Other company" };
const digest = "sha256:" + "a".repeat(64);
const plan = {
  format: "ai-stp-native-inventory-consent/1",
  context: { context_id: a.id, label: a.label },
  policy: { inventory_scan_enabled: true },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(transport.cmdRunRead).mockResolvedValue(ok({ enabled: false }));
  vi.mocked(transport.cliPlan).mockResolvedValue(
    ok({ plan, plan_digest: digest }),
  );
  vi.mocked(transport.cmdNativeInventoryEnable).mockResolvedValue(
    ok({ enabled: true }),
  );
});
afterEach(cleanup);
it("approves the original company disclosure after the selected view changes", async () => {
  const view = render(<NativeInventory context={a} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Review inventory consent" }),
  );
  await screen.findByText("Consent for Original company");
  view.rerender(<NativeInventory context={b} />);
  fireEvent.click(
    screen.getByRole("checkbox", { name: /I approve the disclosed/ }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Enable reviewed consent" }),
  );
  await waitFor(() =>
    expect(transport.cmdNativeInventoryEnable).toHaveBeenCalledWith(
      plan,
      digest,
      true,
    ),
  );
  expect(transport.cliPlan).toHaveBeenCalledWith(
    "corporate inventory consent plan",
    { context: a.id },
  );
});
it("makes no background scan or delivery and disables locally in the chosen original context", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue(
    ok({ enabled: true, pending_digest: digest }),
  );
  vi.mocked(transport.cliApplyConfirmed).mockResolvedValue(
    ok({ enabled: false }),
  );
  render(<NativeInventory context={a} />);
  await screen.findByRole("button", { name: "Disable locally" });
  expect(transport.cliApplyConfirmed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Disable locally" }));
  await waitFor(() =>
    expect(transport.cliApplyConfirmed).toHaveBeenCalledWith(
      "corporate inventory disable",
      { context: a.id },
      [],
      true,
    ),
  );
});
