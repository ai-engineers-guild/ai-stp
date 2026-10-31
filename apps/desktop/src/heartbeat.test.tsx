// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { type ContextView, useContexts } from "./contexts";
import { consentReview, foregroundHeartbeat } from "./heartbeat";
import HeartbeatDelivery from "./components/HeartbeatDelivery";
import ForegroundHeartbeat from "./components/ForegroundHeartbeat";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()), cmdMachineHelp: vi.fn(), cmdRunRead: vi.fn(),
  cliPlan: vi.fn(), cliApplyConfirmed: vi.fn(), cmdHeartbeatConsentApply: vi.fn(),
}));
const A: ContextView = { id: "context_A", label: "Company", mode: "corporate", organization: "Company", origin: "https://company.example.test", connection: "connection_A" };
const digest = `sha256:${"a".repeat(64)}`;
const ok = (data: Record<string, unknown>): CmdResult => ({ ok: true, data, warnings: [], continuations: [], error: null, error_code: null });
const status = (enabled = false, context = A) => ok({ schema_version: 1, context_id: context.id, context_digest: digest,
  enabled, pending: false, attempts: 0, scheduler_registered: false, coverage: "cli_foreground_liveness_only" });
const help = ok({ commands: [["delivery", "read"], ["consent plan", "plan"], ["consent apply", "apply"], ["flush", "apply"], ["disable", "apply"], ["maintain", "apply"]]
  .map(([path, mutability]) => ({ path: ["corporate", "heartbeat", ...path.split(" ")], mutability })) });
const preview = () => {
  const account = { origin: A.origin, connection: { connection_id: A.connection }, account_id: "account_original", device_id: "device_original", public_key: "original" };
  return ok({ context_digest: digest, plan_digest: digest, plan: { schema_version: 1, action: "corporate.heartbeat.consent",
    plan_id: "plan_01ARZ3NDEKTSV4RRFFQ69G5FAV", created_at: "2030-01-01T00:00:00.000Z", expires_at: "2030-01-01T00:10:00.000Z", policy_version: 7,
    policy: { enabled: true, policy_version: 7, interval_seconds: 21600, retry_base_seconds: 60 },
    account, context: { context_id: A.id, authority: { kind: "remote", account, organization: { kind: "corporate" } } } },
    disclosure: { coverage: "cli_foreground_liveness_only", harness_runtime_coverage: "unknown", managed_inventory: "none", startup_service_installed: false } });
};
beforeEach(() => {
  vi.resetAllMocks();
  useContexts.setState({ selected: A, loading: false, switching: false });
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(help);
  vi.mocked(transport.cmdRunRead).mockResolvedValue(status());
  vi.mocked(transport.cliPlan).mockResolvedValue(preview());
  vi.mocked(transport.cliApplyConfirmed).mockResolvedValue(status());
  vi.mocked(transport.cmdHeartbeatConsentApply).mockResolvedValue(status(true));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

it("keeps personal mode and absent consent free from corporate delivery", async () => {
  await foregroundHeartbeat({ ...A, mode: "personal" }, () => true);
  expect(transport.cmdRunRead).not.toHaveBeenCalled();
  expect(transport.cliApplyConfirmed).toHaveBeenCalledExactlyOnceWith("corporate heartbeat maintain", {}, [], true);
  vi.mocked(transport.cliApplyConfirmed).mockClear();
  await foregroundHeartbeat(A, () => true);
  expect(transport.cmdRunRead).toHaveBeenCalledExactlyOnceWith("corporate heartbeat delivery", { context: A.id });
  expect(transport.cliApplyConfirmed).toHaveBeenCalledExactlyOnceWith("corporate heartbeat maintain", {}, [], true);
});

it("rechecks the original visit after asynchronous discovery and local consent reads", async () => {
  let current = true;
  vi.mocked(transport.cmdRunRead).mockImplementation(async () => { current = false; return status(true); });
  await foregroundHeartbeat(A, () => current);
  expect(transport.cliApplyConfirmed).not.toHaveBeenCalledWith("corporate heartbeat flush", expect.anything(), expect.anything(), expect.anything());
  vi.mocked(transport.cliApplyConfirmed).mockClear();
  vi.mocked(transport.cmdMachineHelp).mockImplementation(async () => { current = false; return help; });
  current = true;
  await foregroundHeartbeat(A, () => current);
  expect(transport.cliApplyConfirmed).not.toHaveBeenCalled();
});

it("flushes only the explicitly enabled original context and requires advertised commands", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue(status(true));
  await foregroundHeartbeat(A, () => true);
  expect(transport.cliApplyConfirmed).toHaveBeenLastCalledWith("corporate heartbeat flush", { context: A.id }, [], true);
  vi.mocked(transport.cliApplyConfirmed).mockClear();
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(ok({ commands: [] }));
  await foregroundHeartbeat(A, () => true);
  expect(transport.cliApplyConfirmed).not.toHaveBeenCalled();
});

it("requires the reviewed original context, origin, policy and bounded disclosure", () => {
  expect(consentReview(preview(), A, digest)).not.toBeNull();
  expect(consentReview(preview(), { ...A, id: "context_B" }, digest)).toBeNull();
  expect(consentReview(preview(), { ...A, origin: "https://other.example.test" }, digest)).toBeNull();
  expect(consentReview(preview(), A, `sha256:${"b".repeat(64)}`)).toBeNull();
  const response = preview();
  response.data!.disclosure = { coverage: "all-harnesses" };
  expect(consentReview(response, A, digest)).toBeNull();
});

it("reviews without sending and applies only a frozen, explicitly confirmed plan", async () => {
  const response = preview();
  vi.mocked(transport.cliPlan).mockResolvedValue(response);
  render(<HeartbeatDelivery context={A} help={help} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Review heartbeat consent" }));
  await screen.findByRole("checkbox");
  expect(transport.cliApplyConfirmed).not.toHaveBeenCalled();
  const button = screen.getByRole("button", { name: "Enable reviewed heartbeat reporting" });
  expect(button.hasAttribute("disabled")).toBe(true);
  const original = structuredClone(response.data!.plan);
  (response.data!.plan as Record<string, unknown>).policy_version = 99;
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(button);
  await waitFor(() => expect(transport.cmdHeartbeatConsentApply).toHaveBeenCalledExactlyOnceWith(original, digest, true));
  await screen.findByText(/Local reporting: enabled/);
});

it("discards a late review after leaving and revisiting the same company", async () => {
  let complete!: (value: CmdResult) => void;
  vi.mocked(transport.cliPlan).mockReturnValue(new Promise((resolve) => { complete = resolve; }));
  const { rerender } = render(<HeartbeatDelivery key="A1" context={A} help={help} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Review heartbeat consent" }));
  await waitFor(() => expect(transport.cliPlan).toHaveBeenCalled());
  rerender(<HeartbeatDelivery key="B" context={{ ...A, id: "context_B" }} help={help} disabled={false} />);
  rerender(<HeartbeatDelivery key="A2" context={A} help={help} disabled={false} />);
  await act(async () => complete(preview()));
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(transport.cmdHeartbeatConsentApply).not.toHaveBeenCalled();
});

it("offers offline disable even when a delivery read fails", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue({ ...status(), ok: false, data: null, error: "Unavailable" });
  render(<HeartbeatDelivery context={A} help={help} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Read local delivery" }));
  await screen.findByText("Unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Disable local reporting" }));
  await waitFor(() => expect(transport.cliApplyConfirmed).toHaveBeenCalledExactlyOnceWith("corporate heartbeat disable", { context: A.id }, [], true));
});

it("does not run delivery while the application is unfocused", async () => {
  vi.spyOn(document, "hasFocus").mockReturnValue(false);
  render(<ForegroundHeartbeat />);
  await act(async () => { window.dispatchEvent(new Event("focus")); });
  expect(transport.cmdMachineHelp).not.toHaveBeenCalled();
});
