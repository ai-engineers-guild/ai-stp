// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import CheckoutOperations from "./components/CheckoutOperations";
import { bindingRetirementReceipt, bindingRetirementReview } from "./bindingRetirement";
import { record, useContexts, type ContextView } from "./contexts";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cliPlan: vi.fn(), cmdBindingRetirementApply: vi.fn(), cmdCheckoutApply: vi.fn(),
  cmdMachineHelp: vi.fn(), cmdRunRead: vi.fn(),
}));
const context: ContextView = { id: "context_A", label: "Company", mode: "corporate",
  organization: "Company", origin: "https://company.example.test", connection: "connection_A" };
const path = (value: string) => ({ display: value.normalize("NFC"),
  utf8_base64: btoa(String.fromCharCode(...new TextEncoder().encode(value))) });
const digest = "sha256:" + "a".repeat(64), retirementDigest = "sha256:" + "b".repeat(64);
const account = { account_id: "account_A", origin: context.origin, connection: { connection_id: context.connection } };
const organization = { organization_id: "organization_A" };
const originalContext = { context_id: context.id, label: context.label,
  authority: { kind: "remote", account, organization } };
const root = path("/private/cafe\u0301"), state = path("/private/state");
const link = { link_id: "link_A", organization_id: organization.organization_id,
  local_project_id: "project_A", remote_project_id: "remote_project_A", provider_project_id: null,
  plan_id: "link_plan_A", plan_digest: "sha256:" + "c".repeat(64), revision: 1, state: "linked" };
const snapshot = { context: originalContext, account, organization,
  target: { remote_project_id: link.remote_project_id },
  local_project: { local_project_id: link.local_project_id, root: { path: root, identity: ["10", "20"] } },
};
function original(): Record<string, unknown> {
  return { operation_id: "operation_adopt", plan_digest: digest, state: "completed",
    installation_authority: false, binding_retirement: null,
    plan: { operation_id: "operation_adopt", state_parent: state, checkout_root: root,
      change: { action: "adopt", snapshot, request_operation_id: "operation_request" } },
    effect: { effect: "adopted", link } };
}
const ok = (data: Record<string, unknown>): CmdResult => ({ ok: true, data, error: null,
  error_code: null, warnings: [], continuations: [] });
function proposal(): CmdResult {
  return ok({ plan_digest: retirementDigest, plan: {
    schema_version: 1, operation_id: "operation_retire", state_parent: state,
    registry_schema_before: 59, registry_schema_after: 60,
    snapshot: { context: originalContext, account, organization,
      binding: { source: { operation_id: "operation_adopt", plan_digest: digest },
        request: { operation_id: "operation_request" }, checkout_root: root, physical_root: ["10", "20"],
        local_project: { stable_id: "project_A" }, link },
      remote_link: { ...link, state: "unlinked", revision: 5 } },
  } });
}
function receipt(): Record<string, unknown> {
  return { ...proposal().data, operation_id: "operation_retire", state: "verified",
    outcome: "local_binding_retired", binding_operation_id: "operation_adopt",
    original_request_operation_id: "operation_request", local_binding_retired: true,
    reservation_released: true, remote_write_submitted: false, harness_files_changed: false,
    tasks_changed: false, installation_authority: false };
}
function locationProposal(): CmdResult {
  const value = structuredClone(proposal()), plan = record(value.data!.plan), binding = record(record(plan.snapshot).binding);
  plan.registry_schema_before = 61;
  plan.registry_schema_after = 61;
  binding.checkout_root = path("/private/moved-cafe\u0301");
  binding.location = { operation_id: "operation_01JAXXXXXXXXXXXXXXXXXXXXXX", plan_digest: "sha256:" + "d".repeat(64),
    physical: { kind: "unix", device: "10", inode: "20" } };
  return value;
}
let saved: Record<string, unknown>;
beforeEach(() => {
  vi.resetAllMocks();
  saved = original();
  useContexts.setState({ selected: context, loading: false, switching: false,
    result: ok({ contexts: [{ context: originalContext }] }) });
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(ok({ commands: [
    { path: ["corporate", "project", "link", "list"], mutability: "read" },
    { path: ["corporate", "project", "link", "show"], mutability: "read" },
    { path: ["corporate", "project", "binding-retire", "plan"], mutability: "plan" },
    { path: ["corporate", "project", "binding-retire", "apply"], mutability: "apply" },
  ] }));
  vi.mocked(transport.cmdRunRead).mockImplementation(async (route) =>
    route.endsWith(" list") ? ok({ items: [saved], next_cursor: null }) : ok(saved));
  vi.mocked(transport.cliPlan).mockResolvedValue(proposal());
  vi.mocked(transport.cmdBindingRetirementApply).mockImplementation(async () => {
    const value = receipt(); saved = { ...saved, binding_retirement: value }; return ok(value);
  });
});
afterEach(cleanup);

async function inspect() {
  fireEvent.click(await screen.findByRole("button", { name: "Inspect operation_adopt" }));
  await screen.findByLabelText("Original checkout operation");
}
async function prepare() {
  await inspect();
  fireEvent.click(screen.getByRole("button", { name: "Review local binding retirement" }));
  await screen.findByLabelText("Review local binding retirement");
}
function authorize() {
  fireEvent.click(screen.getByLabelText("I reviewed this exact local binding retirement and authorize releasing its reservation."));
  fireEvent.click(screen.getByRole("button", { name: "Apply reviewed local binding retirement" }));
}

it("separately reviews the exact terminal link, applies only after confirmation and reloads its distinct history", async () => {
  const mounted = render(<CheckoutOperations />);
  await prepare();
  expect(transport.cmdBindingRetirementApply).not.toHaveBeenCalled();
  expect((screen.getByRole("button", { name: "Apply reviewed local binding retirement" }) as HTMLButtonElement).disabled).toBe(true);
  expect(transport.cliPlan).toHaveBeenCalledWith("corporate project binding-retire plan", {
    context: context.id, "binding-operation": "operation_adopt",
  });
  authorize();
  await screen.findByText("This original local binding was retired. Its adoption receipt is preserved.");
  expect(transport.cmdBindingRetirementApply).toHaveBeenCalledWith(proposal().data!.plan, retirementDigest, true);
  expect(transport.cmdCheckoutApply).not.toHaveBeenCalled();
  mounted.unmount();
  render(<CheckoutOperations />);
  await inspect();
  await screen.findByText("This original local binding was retired. Its adoption receipt is preserved.");
  expect(screen.queryByRole("button", { name: "Review local binding retirement" })).toBe(null);
  expect(transport.cliPlan).toHaveBeenCalledTimes(1);
});

it("retains one exact plan after an unconfirmed apply and retries only with another explicit authorization", async () => {
  vi.mocked(transport.cmdBindingRetirementApply).mockResolvedValueOnce({ ...ok({}),
    ok: false, error_code: "AI_STP_TIMEOUT_UNCONFIRMED", error: "Reply unconfirmed" });
  render(<CheckoutOperations />);
  await prepare();
  authorize();
  await screen.findByText("Reply unconfirmed");
  expect(transport.cmdBindingRetirementApply).toHaveBeenCalledTimes(1);
  expect((screen.getByRole("button", { name: "Apply reviewed local binding retirement" }) as HTMLButtonElement).disabled).toBe(true);
  authorize();
  await screen.findByText("This original local binding was retired. Its adoption receipt is preserved.");
  expect(transport.cliPlan).toHaveBeenCalledTimes(1);
  expect(vi.mocked(transport.cmdBindingRetirementApply).mock.calls[0]).toEqual(vi.mocked(transport.cmdBindingRetirementApply).mock.calls[1]);
});

it("discards a late private plan after switching away and back to the original context", async () => {
  let finish!: (value: CmdResult) => void;
  vi.mocked(transport.cliPlan).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<CheckoutOperations />);
  await inspect();
  fireEvent.click(screen.getByRole("button", { name: "Review local binding retirement" }));
  await act(async () => { useContexts.setState({ selected: { ...context, id: "context_B" } }); });
  await act(async () => { useContexts.setState({ selected: context }); });
  await act(async () => finish({ ...proposal(), warnings: ["private-late-plan-warning"] }));
  expect(screen.queryByLabelText("Review local binding retirement")).toBe(null);
  expect(screen.queryByText("private-late-plan-warning")).toBe(null);
  expect(transport.cmdBindingRetirementApply).not.toHaveBeenCalled();
});

it.each(["origin", "account", "context", "source", "request", "project", "physical", "path", "link", "state", "schema"])(
  "refuses a mismatched %s proposal before private content is displayed", async (field) => {
    const bad = structuredClone(proposal()), plan = record(bad.data!.plan), value = record(plan.snapshot),
      binding = record(value.binding);
    if (field === "origin") record(value.account).origin = "https://other.example.test";
    if (field === "account") record(value.account).account_id = "account_other";
    if (field === "context") record(value.context).context_id = "context_other";
    if (field === "source") record(binding.source).plan_digest = retirementDigest;
    if (field === "request") record(binding.request).operation_id = "operation_other";
    if (field === "project") record(binding.local_project).stable_id = "project_other";
    if (field === "physical") binding.physical_root = ["10", "99"];
    if (field === "path") binding.checkout_root = path("/private/café");
    if (field === "link") record(value.remote_link).plan_id = "link_plan_other";
    if (field === "state") record(value.remote_link).state = "linked";
    if (field === "schema") plan.registry_schema_before = "59";
    bad.warnings = ["private-mismatched-warning"];
    vi.mocked(transport.cliPlan).mockResolvedValue(bad);
    render(<CheckoutOperations />);
    await inspect();
    fireEvent.click(screen.getByRole("button", { name: "Review local binding retirement" }));
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("Review local binding retirement")).toBe(null);
    expect(screen.queryByText("private-mismatched-warning")).toBe(null);
    expect(transport.cmdBindingRetirementApply).not.toHaveBeenCalled();
  },
);

it("does not equate a release receipt with remote writes or changes to checkout/tasks", () => {
  expect(bindingRetirementReview(proposal(), context, original())).not.toBe(null);
  expect(bindingRetirementReceipt(receipt(), original())).toBe(true);
  for (const field of ["remote_write_submitted", "harness_files_changed", "tasks_changed", "installation_authority"]) {
    expect(bindingRetirementReceipt({ ...receipt(), [field]: true }, original())).toBe(false);
  }
});

it("retains retirement review and immutable receipt lookup after a reviewed checkout location", () => {
  const value = locationProposal();
  expect(bindingRetirementReview(value, context, original())).not.toBe(null);
  expect(bindingRetirementReceipt({ ...receipt(), plan: value.data!.plan }, original())).toBe(true);
});

it("shows the current byte-preserving checkout before confirming retirement and restores that receipt", async () => {
  const value = locationProposal(), retained = { ...receipt(), plan: value.data!.plan };
  vi.mocked(transport.cliPlan).mockResolvedValue(value);
  vi.mocked(transport.cmdBindingRetirementApply).mockImplementation(async () => {
    saved = { ...saved, binding_retirement: retained }; return ok(retained);
  });
  const mounted = render(<CheckoutOperations />);
  await prepare();
  expect(screen.getByText("/private/moved-cafe\u0301").textContent).toBe("/private/moved-cafe\u0301");
  expect(transport.cmdBindingRetirementApply).not.toHaveBeenCalled();
  authorize();
  await screen.findByText("This original local binding was retired. Its adoption receipt is preserved.");
  expect(transport.cmdBindingRetirementApply).toHaveBeenCalledWith(value.data!.plan, retirementDigest, true);
  mounted.unmount();
  render(<CheckoutOperations />);
  await inspect();
  await screen.findByText("This original local binding was retired. Its adoption receipt is preserved.");
});

it("preserves known61 without a location and rejects future, upgrade and downgrade substitutions", () => {
  for (const [before, after, accepted] of [[61, 61, true], [62, 62, false], [60, 61, false], [61, 60, false]]) {
    const value = structuredClone(proposal()), plan = record(value.data!.plan);
    plan.registry_schema_before = before; plan.registry_schema_after = after;
    expect(bindingRetirementReview(value, context, original()) !== null).toBe(accepted);
  }
});

it.each(["absent", "operation", "digest", "physical", "overflow", "decimal", "unknown"])(
  "refuses a changed checkout with %s location evidence", (field) => {
    const value = locationProposal(), plan = record(value.data!.plan), binding = record(record(plan.snapshot).binding),
      location = record(binding.location), physical = record(location.physical);
    if (field === "absent") delete binding.location;
    if (field === "operation") location.operation_id = "operation_adopt";
    if (field === "digest") location.plan_digest = digest + "0";
    if (field === "physical") physical.inode = "99";
    if (field === "overflow") physical.inode = "18446744073709551616";
    if (field === "decimal") physical.inode = "020";
    if (field === "unknown") physical.extra = true;
    expect(bindingRetirementReview(value, context, original())).toBe(null);
    expect(bindingRetirementReceipt({ ...receipt(), plan }, original())).toBe(false);
  },
);

it("retains a full Windows128 file ID without converting it to an imprecise number", () => {
  const prior = structuredClone(original()), priorPlan = record(prior.plan), before = record(record(priorPlan.change).snapshot),
    value = locationProposal(), plan = record(value.data!.plan), binding = record(record(plan.snapshot).binding);
  priorPlan.checkout_root = path("C:\\original");
  record(record(before.local_project).root).path = priorPlan.checkout_root;
  priorPlan.state_parent = path("C:\\state"); plan.state_parent = priorPlan.state_parent;
  binding.checkout_root = path("C:\\moved-cafe\u0301");
  const physical = { kind: "windows", volume: "10", file_id: "340282366920938463463374607431768211455" };
  record(binding.location).physical = physical;
  expect(bindingRetirementReview(value, context, prior)).not.toBe(null);
  physical.file_id = "340282366920938463463374607431768211456";
  expect(bindingRetirementReview(value, context, prior)).toBe(null);
});
