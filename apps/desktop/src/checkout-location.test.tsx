// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CheckoutLocation from "./components/CheckoutLocation";
import { locationHistory, locationPhysical, locationReceipt, locationReview } from "./checkoutLocation";
import { record, type ContextView } from "./contexts";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cliPlan: vi.fn(), cmdCheckoutLocationApply: vi.fn(), cmdMachineHelp: vi.fn(), cmdRunRead: vi.fn(),
}));
const id = (index: number) => "operation_" + String(index).padStart(26, "0");
const digest = (letter: string) => "sha256:" + letter.repeat(64);
const path = (value: string) => ({ display: value.normalize("NFC"),
  utf8_base64: btoa(String.fromCharCode(...new TextEncoder().encode(value))) });
const context: ContextView = { id: "context_A", label: "Company", mode: "corporate", organization: "Company",
  origin: "https://company.example.test", connection: "connection_A" };
const account = { origin: context.origin, account_id: "account_A", connection: { connection_id: context.connection } };
const organization = { organization_id: "organization_A" };
const owner = { account_id: "account_private", device_id: "device_private" };
const state = path("/private/state"), root = path("/private/cafe\u0301"), moved = path("/private/moved-cafe\u0301");
const originalContext = { context_id: context.id, label: context.label, root: state, local_identity: owner,
  authority: { kind: "remote", account, organization } };
const link = { link_id: "link_A", organization_id: organization.organization_id, local_project_id: "project_A",
  remote_project_id: "remote_project_A", provider_project_id: null, plan_id: "link_plan_A", plan_digest: digest("c"), state: "linked" };
const physical = { kind: "unix", device: "10", inode: "20" };
const snapshot = { context: originalContext, account, organization, target: { remote_project_id: link.remote_project_id },
  local_project: { local_project_id: "project_A", root: { path: root, identity: ["10", "20"] } } };
const original = { operation_id: id(1), plan_digest: digest("a"), state: "completed", binding_retirement: null, installation_authority: false,
  plan: { operation_id: id(1), state_parent: state, checkout_root: root,
    change: { action: "adopt", snapshot, request_operation_id: id(0) } }, effect: { effect: "adopted", link } };
const ok = (data: Record<string, unknown>): CmdResult => ({ ok: true, data, warnings: [], continuations: [], error: null, error_code: null });
function proposal(action: "anchor" | "relocate" = "anchor"): CmdResult {
  const binding = { source: { operation_id: id(1), plan_digest: digest("a") }, request: { operation_id: id(0), plan_digest: digest("d") },
    context: originalContext, account, checkout_root: root, physical_root: ["10", "20"], local_project: { stable_id: "project_A" }, link,
    reservation: { binding_operation_id: id(1), request_operation_id: id(0), local_project_id: "project_A" },
    ...(action === "relocate" ? { location: { operation_id: id(2), plan_digest: digest("b"), physical } } : {}) };
  return ok({ plan_digest: digest(action === "anchor" ? "b" : "e"), plan: {
    schema_version: 1, operation_id: id(action === "anchor" ? 2 : 3), action, state_parent: state,
    created_at: "2026-10-29T12:00:00.000Z", expires_at: "2026-10-29T12:15:00.000Z",
    registry_schema_before: action === "anchor" ? 59 : 61, registry_schema_after: 61,
    local_identity: owner, binding, original: original.plan,
    reader: { context: originalContext, account, organization }, remote: { state: "applied", link },
    destination: action === "anchor" ? root : moved, checkout_spelling: action === "anchor" ? root : moved,
    physical, git_physical: { ...physical, inode: "21" },
    relocation: action === "anchor" ? null : { root: moved, previous_root: root, previous: binding.local_project, root_identity: ["10", "20"] },
  } });
}
function receipt(action: "anchor" | "relocate" = "anchor"): Record<string, unknown> {
  const value = proposal(action).data!, plan = record(value.plan);
  return { ...value, operation_id: plan.operation_id, binding_operation_id: id(1), state: "verified",
    outcome: action === "anchor" ? "location_anchored" : "checkout_relocated", remote_write_submitted: false,
    harness_files_changed: false, tasks_changed: false, installation_authority: false };
}
function history(indices: number[] = [], cursor: string | null = null): CmdResult {
  return ok({ schema_version: 1, binding_operation_id: id(1), installation_authority: false, next_cursor: cursor,
    locations: indices.map((index) => ({ operation_id: id(index), plan_digest: digest(index === 2 ? "b" : "e"),
      action: index === 2 ? "anchor" : "relocate", root: index === 2 ? root : moved, state: "verified",
      created_at: "2026-10-29T12:00:00.000Z", completed_at: "2026-10-29T12:00:01.000Z" })) });
}
const onBusy = vi.fn();
function view(selected = context) { return <CheckoutLocation key={selected.id} original={original} context={selected}
  reader={selected.id} disabled={false} onBusyChange={onBusy} />; }
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(ok({ commands: [
    ["corporate project location list", "read"], ["corporate project location show", "read"],
    ["corporate project location-anchor plan", "plan"], ["corporate project location-relocate plan", "plan"],
    ["corporate project location apply", "apply"],
  ].map(([route, mutability]) => ({ path: route.split(" "), mutability })) }));
  vi.mocked(transport.cmdRunRead).mockImplementation(async (route) => route.endsWith(" list") ? history() : ok(receipt()));
  vi.mocked(transport.cliPlan).mockResolvedValue(proposal());
  vi.mocked(transport.cmdCheckoutLocationApply).mockResolvedValue(ok(receipt()));
});
afterEach(cleanup);
async function prepare() {
  const button = await screen.findByRole("button", { name: "Review checkout anchor" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(button);
  await screen.findByLabelText("Review checkout location");
}
function authorize() {
  fireEvent.click(screen.getByLabelText("I reviewed this exact checkout location and authorize saving its metadata."));
  fireEvent.click(screen.getByRole("button", { name: "Apply reviewed checkout location" }));
}

it("separates the immutable adoption from explicit anchor review and exact terminal apply", async () => {
  render(view()); await prepare();
  expect(transport.cliPlan).toHaveBeenCalledWith("corporate project location-anchor plan", { context: context.id, "binding-operation": id(1) });
  expect((screen.getByRole("button", { name: "Apply reviewed checkout location" }) as HTMLButtonElement).disabled).toBe(true);
  expect(transport.cmdCheckoutLocationApply).not.toHaveBeenCalled();
  authorize();
  await screen.findByText("Checkout anchor receipt saved.");
  expect(transport.cmdCheckoutLocationApply).toHaveBeenCalledWith(proposal().data!.plan, digest("b"), true, undefined);
  expect(screen.getAllByText("/private/cafe\u0301").length).toBeGreaterThan(0);
});

it("retains the exact plan and trusted executable after an unconfirmed reply", async () => {
  vi.mocked(transport.cmdCheckoutLocationApply).mockResolvedValueOnce({ ...ok({}), ok: false, error_code: "IPC_THROW", error: "Reply unconfirmed" });
  render(view());
  const git = await screen.findByLabelText("Trusted Git executable for location review (optional)");
  fireEvent.change(git, { target: { value: "/trusted/git" } });
  await prepare(); authorize();
  await screen.findByText("Reply unconfirmed");
  expect((screen.getByRole("button", { name: "Apply reviewed checkout location" }) as HTMLButtonElement).disabled).toBe(true);
  authorize(); await screen.findByText("Checkout anchor receipt saved.");
  expect(transport.cliPlan).toHaveBeenCalledTimes(1);
  expect(vi.mocked(transport.cmdCheckoutLocationApply).mock.calls[0]).toEqual(vi.mocked(transport.cmdCheckoutLocationApply).mock.calls[1]);
  expect(transport.cmdCheckoutLocationApply).toHaveBeenLastCalledWith(proposal().data!.plan, digest("b"), true, "/trusted/git");
});

it("reads a committed unknown reply through the exact offline operation instead of creating another plan", async () => {
  vi.mocked(transport.cmdCheckoutLocationApply).mockResolvedValue({ ...ok({}), ok: false, error_code: "IPC_THROW", error: "Reply unconfirmed" });
  render(view()); await prepare(); authorize(); await screen.findByText("Reply unconfirmed");
  fireEvent.click(screen.getByRole("button", { name: "Read this location outcome" }));
  await screen.findByText("Checkout anchor receipt saved.");
  expect(transport.cmdRunRead).toHaveBeenLastCalledWith("corporate project location show", { operation: id(2) });
  expect(transport.cliPlan).toHaveBeenCalledTimes(1);
  expect(transport.cmdCheckoutLocationApply).toHaveBeenCalledTimes(1);
});

it("clears the previous receipt while a different exact historical operation is still being read", async () => {
  let finish!: (response: CmdResult) => void;
  vi.mocked(transport.cmdRunRead).mockImplementation(async (route) => route.endsWith(" list") ? history([3, 2]) :
    new Promise<CmdResult>((resolve) => { finish = resolve; }));
  render(view()); await prepare(); authorize();
  await screen.findByText("Checkout anchor receipt saved.");
  fireEvent.click(screen.getByRole("button", { name: "Inspect location " + id(3) }));
  await waitFor(() => expect(screen.queryByLabelText("Recorded location receipt")).toBe(null));
  expect(screen.queryByText("Checkout anchor receipt saved.")).toBe(null);
  await act(async () => finish(ok(receipt("relocate"))));
  await screen.findByText("Checkout relocation receipt saved.");
  expect(transport.cmdRunRead).toHaveBeenLastCalledWith("corporate project location show", { operation: id(3) });
  expect(transport.cmdCheckoutLocationApply).toHaveBeenCalledTimes(1);
});

it("reviews the exact NFD destination without replacing the immutable adoption pathname", async () => {
  vi.mocked(transport.cliPlan).mockResolvedValue(proposal("relocate"));
  render(view());
  const field = await screen.findByLabelText("Existing moved checkout directory");
  fireEvent.change(field, { target: { value: "/private/moved-cafe\u0301" } });
  const button = screen.getByRole("button", { name: "Review moved checkout" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false)); fireEvent.click(button);
  await screen.findByLabelText("Review checkout location");
  expect(transport.cliPlan).toHaveBeenLastCalledWith("corporate project location-relocate plan", { context: context.id,
    "binding-operation": id(1), root: "/private/moved-cafe\u0301" });
  expect(screen.getByText("/private/moved-cafe\u0301").textContent).toBe("/private/moved-cafe\u0301");
  expect(locationReview(proposal("relocate"), "relocate", context, original, "/private/moved-café")).toBe(null);
});

it("discards a private late plan after switching away and back", async () => {
  let finish!: (response: CmdResult) => void;
  vi.mocked(transport.cliPlan).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const mounted = render(view());
  const button = await screen.findByRole("button", { name: "Review checkout anchor" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false)); fireEvent.click(button);
  mounted.rerender(view({ ...context, id: "context_B" })); mounted.rerender(view());
  await act(async () => finish({ ...proposal(), warnings: ["private-late-warning"] }));
  expect(screen.queryByLabelText("Review checkout location")).toBe(null);
  expect(screen.queryByText("private-late-warning")).toBe(null);
  expect(transport.cmdCheckoutLocationApply).not.toHaveBeenCalled();
});

it("restores immutable offline receipts across restarts and after a future relocation or retirement", async () => {
  vi.mocked(transport.cmdRunRead).mockImplementation(async (route) => route.endsWith(" list") ? history([3, 2]) : ok(receipt()));
  const retired = { ...original, binding_retirement: { state: "verified" } };
  render(<CheckoutLocation original={retired} context={null} reader={undefined} disabled={false} onBusyChange={onBusy} />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect location " + id(2) }));
  await screen.findByText("Checkout anchor receipt saved.");
  expect(screen.queryByRole("button", { name: "Review checkout anchor" })).toBe(null);
  expect(transport.cliPlan).not.toHaveBeenCalled();
  expect(locationReceipt(receipt(), retired)?.plan.destination).toEqual(root);
});

it("pages the original binding's offline history using its exact continuation", async () => {
  const indices = Array.from({ length: 100 }, (_, index) => 200 - index);
  vi.mocked(transport.cmdRunRead).mockResolvedValueOnce(history(indices, id(101))).mockResolvedValueOnce(history([100, 99]));
  render(view());
  fireEvent.click(await screen.findByRole("button", { name: "Read more location history" }));
  await screen.findByRole("button", { name: "Inspect location " + id(99) });
  expect(transport.cmdRunRead).toHaveBeenLastCalledWith("corporate project location list", { "binding-operation": id(1), cursor: id(101) });
  expect(screen.queryByRole("button", { name: "Read more location history" })).toBe(null);
  expect(transport.cliPlan).not.toHaveBeenCalled();
});

it("requires the selected current company and connection for new reviews while leaving offline receipts readable", () => {
  expect(locationReview(proposal(), "anchor", { ...context, mode: "personal" }, original)).toBe(null);
  expect(locationReview(proposal(), "anchor", { ...context, connection: "connection_other" }, original)).toBe(null);
  expect(locationReview(proposal(), "anchor", { ...context, id: "context_other" }, original)).toBe(null);
  expect(locationReceipt(receipt(), original)).not.toBe(null);
});

it("offers a fresh native review directly from an adoption apply receipt without inferring current binding state", async () => {
  const applied: Record<string, unknown> = { ...original };
  delete applied.binding_retirement;
  render(<CheckoutLocation original={applied} context={context} reader={context.id} disabled={false} onBusyChange={onBusy} />);
  await prepare();
  expect(transport.cliPlan).toHaveBeenLastCalledWith("corporate project location-anchor plan", { context: context.id, "binding-operation": id(1) });
  expect(transport.cmdCheckoutLocationApply).not.toHaveBeenCalled();
});

it.each(["original", "origin", "account", "company", "context", "request", "source", "reservation", "physical", "schema", "root", "locator"])(
  "refuses mismatched %s before rendering a private review", async (field) => {
    const response = structuredClone(proposal()), plan = record(response.data!.plan), binding = record(plan.binding), reader = record(plan.reader);
    if (field === "original") record(plan.original).operation_id = id(8);
    if (field === "origin") record(reader.account).origin = "https://other.example.test";
    if (field === "account") record(reader.account).account_id = "account_other";
    if (field === "company") record(reader.organization).organization_id = "organization_other";
    if (field === "context") record(reader.context).context_id = "context_other";
    if (field === "request") record(binding.request).operation_id = id(9);
    if (field === "source") record(binding.source).plan_digest = digest("f");
    if (field === "reservation") record(binding.reservation).binding_operation_id = id(9);
    if (field === "physical") record(plan.physical).inode = "99";
    if (field === "schema") plan.registry_schema_before = 62;
    if (field === "root") plan.destination = path("/private/café");
    if (field === "locator") binding.location = { operation_id: plan.operation_id, plan_digest: digest("b"), physical };
    response.warnings = ["private-mismatched-warning"];
    vi.mocked(transport.cliPlan).mockResolvedValue(response);
    render(view()); const button = await screen.findByRole("button", { name: "Review checkout anchor" });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false)); fireEvent.click(button);
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("Review checkout location")).toBe(null);
    expect(screen.queryByText("private-mismatched-warning")).toBe(null);
    expect(transport.cmdCheckoutLocationApply).not.toHaveBeenCalled();
  },
);

it("preserves full Windows high bits and refuses noncanonical, overflow and unknown physical identities", () => {
  expect(locationPhysical({ kind: "windows", volume: "18446744073709551615", file_id: "340282366920938463463374607431768211455" })).toBe(true);
  for (const value of [
    { kind: "unix", device: "01", inode: "20" }, { kind: "unix", device: 10, inode: "20" },
    { kind: "unix", device: "10", inode: "18446744073709551616" },
    { kind: "windows", volume: "10", file_id: "340282366920938463463374607431768211456" },
    { kind: "windows", volume: "10", file_id: "-1" }, { kind: "windows", volume: "10", file_id: "20", truncated: true },
  ]) expect(locationPhysical(value)).toBe(false);
});

it("refuses history from another binding, duplicate IDs, malformed paths and forged continuation cursors", () => {
  expect(locationHistory(history([3, 2]), id(1))?.entries).toHaveLength(2);
  expect(locationHistory(history([3, 2]), id(9))).toBe(null);
  expect(locationHistory(history([2, 2]), id(1))).toBe(null);
  expect(locationHistory(history([2], id(2)), id(1))).toBe(null);
  const malformed = history([2]); record((malformed.data!.locations as unknown[])[0]).root = path("relative");
  expect(locationHistory(malformed, id(1))).toBe(null);
});

it("refuses receipt effects, changed plans and an outcome belonging to another operation", () => {
  expect(locationReceipt(receipt(), original)?.digest).toBe(digest("b"));
  expect(locationReview(proposal("relocate"), "relocate", context, original, "/private/moved-cafe\u0301")).not.toBe(null);
  for (const field of ["remote_write_submitted", "harness_files_changed", "tasks_changed", "installation_authority"])
    expect(locationReceipt({ ...receipt(), [field]: true }, original)).toBe(null);
  expect(locationReceipt({ ...receipt(), operation_id: id(9) }, original)).toBe(null);
});
