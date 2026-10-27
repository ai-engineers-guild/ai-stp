// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import CheckoutPreview from "./components/CheckoutPreview";
import CheckoutOperations from "./components/CheckoutOperations";
import { record, useContexts, type ContextView } from "./contexts";
import * as transport from "./transport";
import type { CmdResult } from "./transport";
import { checkoutPath, checkoutReview, type CheckoutAction } from "./checkoutLinks";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cliPlan: vi.fn(), cmdCheckoutApply: vi.fn(), cmdMachineHelp: vi.fn(), cmdRunRead: vi.fn(),
}));
const context: ContextView = { id: "context_A", label: "First", mode: "corporate",
  organization: "First company", origin: "https://first.example.test", connection: "connection_A" };
const project = { id: "remote_project_first", name: "First project" };
const root = "/private/checkout";
const wirePath = (value: string) => ({ display: value.normalize("NFC"),
  utf8_base64: btoa(String.fromCharCode(...new TextEncoder().encode(value))) });
const account = { origin: context.origin, account_id: "account_first", connection: { connection_id: context.connection } };
const organization = { organization_id: "organization_first", display_name: "First company" };
const snapshot = {
  context: { context_id: context.id, label: context.label, authority: { kind: "remote", account, organization } },
  account, organization, target: { remote_project_id: project.id, organization_id: organization.organization_id, providers: [] },
  local_project: { local_project_id: "project_private", root: { path: wirePath(root), identity: ["10", "20"] } },
  request_coordinates: { remote_project_id: project.id, provider_project_id: null },
  selected_provider: null, checkout: { checkout: { commit: "a".repeat(40) } },
};
const ok = (data: Record<string, unknown> = {}): CmdResult => ({
  ok: true, data, error: null, error_code: null, warnings: [], continuations: [],
});
function proposal(action: CheckoutAction): CmdResult {
  return ok({ plan_digest: "sha256:" + ({ request: "a", confirm: "b", adopt: "c" }[action]).repeat(64),
    plan: { operation_id: "operation_" + action, checkout_root: wirePath(root),
      change: { action, snapshot, ...(action === "request" ? {} : { request_operation_id: "operation_request" }) } } });
}
function receipt(action: CheckoutAction, state = "completed"): Record<string, unknown> {
  const value = proposal(action).data!;
  return { ...value, operation_id: record(value.plan).operation_id, state, installation_authority: false,
    effect: { effect: { request: "requested", confirm: "confirmed", adopt: "adopted" }[action] } };
}
const preview = () => ok({ preview: { ...snapshot, online_verified: true, observation_only: true,
  installation_authority: false, link_created: false, binding_created: false, request_admitted: false } });
const help = ok({ commands: [
  { path: ["corporate", "project", "link", "list"], mutability: "read" },
  { path: ["corporate", "project", "link", "show"], mutability: "read" },
  { path: ["corporate", "project", "link", "apply"], mutability: "apply" },
] });
function view(selected = context) {
  return <MemoryRouter><CheckoutPreview key={selected.id} context={selected} project={project} disabled={false} linking /></MemoryRouter>;
}
async function prepare() {
  fireEvent.change(screen.getByLabelText("Checkout directory"), { target: { value: root } });
  fireEvent.click(screen.getByRole("button", { name: "Preview checkout" }));
  await screen.findByText("Checkout verified for review");
}
async function authorize() {
  const apply = screen.getByRole("button", { name: "Apply reviewed checkout change" });
  expect((apply as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByLabelText("I reviewed this exact checkout plan and authorize its change."));
  fireEvent.click(apply);
}
beforeEach(() => {
  vi.resetAllMocks();
  useContexts.setState({ selected: context, loading: false, switching: false,
    result: ok({ contexts: [{ context: snapshot.context }] }) });
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(help);
  vi.mocked(transport.cliPlan).mockImplementation(async (path) => path.endsWith("link-preview") ? preview() :
    proposal(path.includes("link-request") ? "request" : path.includes("link-confirm") ? "confirm" : "adopt"));
  vi.mocked(transport.cmdCheckoutApply).mockImplementation(async (plan) =>
    ok(receipt(record(record(plan).change).action as CheckoutAction)));
  vi.mocked(transport.cmdRunRead).mockResolvedValue(ok({ items: [], next_cursor: null }));
});
afterEach(cleanup);

it.each(["/private/cafe\u0301", "C:\\Users\\fixture\\café", "\\\\server\\share\\project"])(
  "preserves the exact native path bytes for %s", (path) => {
    expect(checkoutPath(wirePath(path))).toBe(path);
  },
);

it.each([
  root,
  { ...wirePath(root), display: "/another/root" },
  { display: "/", utf8_base64: "L/8=" },
  { display: "/\0", utf8_base64: "LwA=" },
  { ...wirePath(root), utf8_base64: wirePath(root).utf8_base64.replace(/=+$/, "") },
  wirePath("relative/root"),
])("refuses malformed or unsupported native path evidence %#", (value) => {
  expect(checkoutPath(value)).toBe(null);
});

it("refuses equal-display roots with different native UTF-8 bytes", () => {
  const anchor = structuredClone(snapshot);
  anchor.local_project.root.path = wirePath("/private/cafe\u0301");
  const response = structuredClone(proposal("request"));
  const plan = record(response.data!.plan);
  const current = record(record(plan.change).snapshot);
  record(current.local_project).root = { path: wirePath("/private/café"), identity: ["10", "20"] };
  plan.checkout_root = wirePath("/private/café");
  expect(checkoutReview(response, "request", context, project.id, anchor)).toBe(null);
});

it("separately reviews and authorizes request, confirmation and local binding through exact native plans", async () => {
  render(view());
  await prepare();
  for (const [action, label] of [["request", "Review link request"], ["confirm", "Review link confirmation"], ["adopt", "Review local binding"]] as const) {
    fireEvent.click(screen.getByRole("button", { name: label }));
    await screen.findByLabelText("Review corporate checkout change");
    expect(transport.cmdCheckoutApply).toHaveBeenCalledTimes({ request: 0, confirm: 1, adopt: 2 }[action]);
    await authorize();
    await waitFor(() => expect(screen.queryByLabelText("Review corporate checkout change")).toBe(null));
    expect(transport.cmdCheckoutApply).toHaveBeenLastCalledWith(proposal(action).data!.plan,
      proposal(action).data!.plan_digest, true, context.id, undefined);
  }
  await screen.findByText("Corporate project binding saved.");
  expect(transport.cliPlan).toHaveBeenCalledTimes(4);
  expect(transport.cmdCheckoutApply).toHaveBeenCalledTimes(3);
});

it("retains the exact request after an unconfirmed reply and never starts another request automatically", async () => {
  vi.mocked(transport.cmdCheckoutApply).mockResolvedValue({ ...ok(), ok: false, error_code: "UNAVAILABLE", error: "Outcome unconfirmed" });
  render(view());
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "Review link request" }));
  await screen.findByLabelText("Review corporate checkout change");
  await authorize();
  await screen.findByText("Outcome unconfirmed");
  expect(transport.cliPlan).toHaveBeenCalledTimes(2);
  expect(transport.cmdCheckoutApply).toHaveBeenCalledTimes(1);
  expect((screen.getByRole("button", { name: "Apply reviewed checkout change" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByLabelText("Retained checkout operation").textContent).toContain("operation_request");
  expect(screen.queryByRole("button", { name: "Review link confirmation" })).toBe(null);
});

it.each(["context", "account", "project", "physical", "request"])("refuses mismatched %s plan coordinates before displaying private content", async (field) => {
  const bad = JSON.parse(JSON.stringify(proposal("request"))) as CmdResult;
  const plan = record(bad.data!.plan), change = record(plan.change), data = record(change.snapshot);
  if (field === "context") record(data.context).context_id = "context_other";
  if (field === "account") record(data.account).account_id = "account_other";
  if (field === "project") record(data.target).remote_project_id = "project_other";
  if (field === "physical") record(record(data.local_project).root).identity = ["10", "999"];
  if (field === "request") change.action = "confirm";
  bad.warnings = ["private-other-company-warning"];
  vi.mocked(transport.cliPlan).mockResolvedValueOnce(preview()).mockResolvedValueOnce(bad);
  render(view());
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "Review link request" }));
  await screen.findByRole("alert");
  expect(screen.queryByText("private-other-company-warning")).toBe(null);
  expect(screen.queryByLabelText("Review corporate checkout change")).toBe(null);
  expect(transport.cmdCheckoutApply).not.toHaveBeenCalled();
});

it("discards a late request review after switching away and back to the same company", async () => {
  let finish!: (value: CmdResult) => void;
  vi.mocked(transport.cliPlan).mockResolvedValueOnce(preview()).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const mounted = render(view());
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "Review link request" }));
  mounted.rerender(view({ ...context, id: "context_B" }));
  mounted.rerender(view());
  await act(async () => finish({ ...proposal("request"), warnings: ["stale-company-warning"] }));
  expect(screen.queryByLabelText("Review corporate checkout change")).toBe(null);
  expect(screen.queryByText("stale-company-warning")).toBe(null);
  expect(transport.cmdCheckoutApply).not.toHaveBeenCalled();
});

it("loads original unknown intent after remount and reconciles through the matching current account/company", async () => {
  const original = receipt("confirm", "interrupted");
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) => path.endsWith("list") ? ok({ items: [original], next_cursor: null }) : ok(original));
  const mounted = render(<CheckoutOperations />);
  await screen.findByRole("button", { name: "Inspect operation_confirm" });
  mounted.unmount();
  render(<CheckoutOperations />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect operation_confirm" }));
  await screen.findByLabelText("Original checkout operation");
  expect(transport.cmdCheckoutApply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText("I reviewed this original intent and authorize outcome reconciliation."));
  fireEvent.click(screen.getByRole("button", { name: "Reconcile original outcome" }));
  await waitFor(() => expect(transport.cmdCheckoutApply).toHaveBeenCalledWith(proposal("confirm").data!.plan,
    proposal("confirm").data!.plan_digest, true, context.id));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Reconcile original outcome" })).toBe(null));
});

it("does not authorize reconciliation under another account, even at the same server and company", async () => {
  const original = receipt("confirm", "applying");
  useContexts.setState({ result: ok({ contexts: [{ context: { ...snapshot.context,
    authority: { ...snapshot.context.authority, account: { ...account, account_id: "another_account" } } } }] }) });
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) => path.endsWith("list") ? ok({ items: [original], next_cursor: null }) : ok(original));
  render(<CheckoutOperations />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect operation_confirm" }));
  await screen.findByLabelText("Original checkout operation");
  expect((screen.getByRole("button", { name: "Reconcile original outcome" }) as HTMLButtonElement).disabled).toBe(true);
  expect(transport.cmdCheckoutApply).not.toHaveBeenCalled();
});

it("continues a retained completed request through separately reviewed confirmation and binding", async () => {
  const original = receipt("request");
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) => path.endsWith("list") ? ok({ items: [original], next_cursor: null }) : ok(original));
  render(<CheckoutOperations />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect operation_request" }));
  await screen.findByLabelText("Original checkout operation");
  for (const [action, label] of [["confirm", "Review original confirmation"], ["adopt", "Review original local binding"]] as const) {
    fireEvent.click(screen.getByRole("button", { name: label }));
    await screen.findByLabelText("Review retained checkout next change");
    expect(transport.cmdCheckoutApply).toHaveBeenCalledTimes(action === "confirm" ? 0 : 1);
    fireEvent.click(screen.getByLabelText("I reviewed this exact retained checkout change and authorize it."));
    fireEvent.click(screen.getByRole("button", { name: "Apply reviewed original checkout change" }));
    await waitFor(() => expect(screen.queryByLabelText("Review retained checkout next change")).toBe(null));
    expect(transport.cmdCheckoutApply).toHaveBeenLastCalledWith(proposal(action).data!.plan,
      proposal(action).data!.plan_digest, true, context.id, undefined);
  }
  await screen.findByText("Original corporate project binding receipt saved.");
  expect(transport.cmdCheckoutApply).toHaveBeenCalledTimes(2);
});
