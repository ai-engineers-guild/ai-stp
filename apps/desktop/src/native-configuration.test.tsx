// @vitest-environment jsdom
import { required } from "./test-values";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import TargetsPage from "./pages/TargetsPage";
import { useContexts } from "./contexts";
import { useApp } from "./store";
import * as transport from "./transport";
import type { CmdResult } from "./transport";
import {
  confirmationCommand,
  nativeReview,
  nativePending,
  nativeStatus,
} from "./nativeConfiguration";
vi.mock("./transport", () => ({
  cmdRunRead: vi.fn(),
  cliPlan: vi.fn(),
  cliApplyConfirmed: vi.fn(),
  cmdNativeConfigurationPlan: vi.fn(),
  cmdNativeConfigurationPrepare: vi.fn(),
}));
const A = "context_01ARZ3NDEKTSV4RRFFQ69G5FAV",
  B = "context_01ARZ3NDEKTSV4RRFFQ69G5FAW";
const OP = "operation_01ARZ3NDEKTSV4RRFFQ69G5FAV",
  DIGEST = `sha256:${"a".repeat(64)}`;
const ok = (data: Record<string, unknown>): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
const context = {
  context_id: A,
  label: "Original personal",
  root: { display: "/normalized", utf8_base64: btoa("/original state") },
};
const plan = {
  format: "ai-stp-native-custody-review/1",
  operation_id: OP,
  native_plan: {
    format: "ai-stp-native-installation/1",
    operation_id: OP,
    context,
    target: { harness_id: "codex" },
  },
  publications: [],
  activation: { sessions: [] },
};
const reviewed = ok({ plan, plan_digest: DIGEST });
const originalRefresh = useContexts.getState().refresh;
beforeEach(() => {
  vi.resetAllMocks();
  useApp.setState({
    capabilities: ok({
      os: "linux",
      native_configuration: { available: true, harnesses: ["codex"] },
    }),
  });
  useContexts.setState({
    selected: {
      id: A,
      label: "Original personal",
      mode: "personal",
      organization: null,
      origin: null,
      connection: null,
    },
    views: [],
    refresh: vi.fn().mockResolvedValue(undefined),
  });
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) =>
    ok(
      path === "configuration native pending"
        ? { pending: null, other_state_pending: false }
        : { setups: [] },
    ),
  );
  vi.mocked(transport.cmdNativeConfigurationPrepare).mockResolvedValue(
    ok({ configuration_changed: false }),
  );
  vi.mocked(transport.cliApplyConfirmed).mockResolvedValue(
    ok({ kind: "native.configuration.configured" }),
  );
});
afterEach(() => {
  cleanup();
  useContexts.setState({ refresh: originalRefresh });
});
it("takes an exact catalog selection straight to folder review without re-entering coordinates", async () => {
  vi.mocked(transport.cmdNativeConfigurationPlan).mockResolvedValue(reviewed);
  const setup = "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV";
  render(
    <MemoryRouter
      initialEntries={[
        `/targets?setup=${setup}&version=1.0&digest=${encodeURIComponent(DIGEST)}&harness=codex`,
      ]}
    >
      <TargetsPage />
    </MemoryRouter>,
  );
  expect(
    screen.getByLabelText("Setup progress").querySelectorAll("li").length,
  ).toBe(4);
  expect(
    screen
      .getByText("Exact setup coordinates")
      .parentElement?.hasAttribute("open"),
  ).toBe(false);
  const button = screen.getByRole("button", {
    name: "Review setup",
  }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(
    screen.getByText("Choose at least one configuration folder to continue."),
  ).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Global configuration folder"), {
    target: { value: "/my/config" },
  });
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  await waitFor(() =>
    expect(transport.cmdNativeConfigurationPlan).toHaveBeenCalledWith(A, {
      schema_version: 1,
      setup: { stable_id: setup, version: "1.0", passport_digest: DIGEST },
      harness_id: "codex",
      operation: "install",
      roots: { global: "/my/config" },
      trust: "pinned",
    }),
  );
  await screen.findByRole("checkbox", {
    name: /I reviewed these exact effects/,
  });
  expect(transport.cmdNativeConfigurationPrepare).not.toHaveBeenCalled();
});
it("retains the reviewed original context when the current view changes before preparation", async () => {
  vi.mocked(transport.cmdNativeConfigurationPlan).mockResolvedValue(reviewed);
  render(
    <MemoryRouter>
      <TargetsPage />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("Setup ID"), {
    target: { value: "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV" },
  });
  fireEvent.change(screen.getByLabelText("Exact version"), {
    target: { value: "1.0" },
  });
  fireEvent.change(screen.getByLabelText("Passport digest"), {
    target: { value: DIGEST },
  });
  fireEvent.change(screen.getByLabelText("Global configuration folder"), {
    target: { value: "/fixture/config" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Review setup" }));
  await screen.findByText(/Original personal · codex/);
  expect(transport.cmdNativeConfigurationPlan).toHaveBeenCalledWith(
    A,
    expect.any(Object),
  );
  act(() =>
    useContexts.setState({
      selected: {
        id: B,
        label: "Second view",
        mode: "personal",
        organization: null,
        origin: null,
        connection: null,
      },
    }),
  );
  expect(
    screen.getByText(/This operation keeps its original context/),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("checkbox", { name: /I reviewed these exact effects/ }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare reviewed setup" }),
  );
  await waitFor(() =>
    expect(transport.cmdNativeConfigurationPrepare).toHaveBeenCalledWith(
      plan,
      DIGEST,
      true,
    ),
  );
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Apply when sessions are stopped",
    }),
  );
  await waitFor(() =>
    expect(transport.cliApplyConfirmed).toHaveBeenCalledWith(
      "configuration native apply",
      { operation: OP, "plan-digest": DIGEST },
      [],
      true,
    ),
  );
});
it("recovers a pending operation without a plan file or selected-context retargeting", async () => {
  useContexts.setState({
    selected: {
      id: B,
      label: "Second view",
      mode: "personal",
      organization: null,
      origin: null,
      connection: null,
    },
  });
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) =>
    ok(
      path === "configuration native pending"
        ? {
            pending: {
              operation_id: OP,
              plan_digest: DIGEST,
              original_context: context,
              harness_id: "codex",
              custody: { state: "applying" },
            },
          }
        : { setups: [] },
    ),
  );
  render(
    <MemoryRouter>
      <TargetsPage />
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Resume original operation" }),
  );
  await waitFor(() =>
    expect(transport.cliApplyConfirmed).toHaveBeenCalledWith(
      "configuration native apply",
      { operation: OP, "plan-digest": DIGEST },
      [],
      true,
    ),
  );
  expect(transport.cmdNativeConfigurationPlan).not.toHaveBeenCalled();
  expect(transport.cmdNativeConfigurationPrepare).not.toHaveBeenCalled();
});
it("copies the raw original state spelling rather than a normalized display path", () => {
  const operation = nativeReview(reviewed);
  expect(operation).not.toBeNull();
  expect(confirmationCommand(required(operation), "linux")).toContain(
    "'/original state'",
  );
  expect(confirmationCommand(required(operation), "linux")).not.toContain(
    "normalized",
  );
  expect(
    nativeReview(
      ok({ plan: { ...plan, operation_id: "other" }, plan_digest: DIGEST }),
    ),
  ).toBeNull();
});

it("refuses malformed JSON identities and phases without invoking object coercion", () => {
  const malformed = JSON.parse('{"toString":"not callable"}') as unknown;
  for (const field of ["operation_id", "plan_digest"]) {
    expect(
      nativeReview(
        field === "operation_id"
          ? ok({
              plan: { ...plan, operation_id: malformed },
              plan_digest: DIGEST,
            })
          : ok({ plan, plan_digest: malformed }),
      ),
    ).toBeNull();
    expect(
      nativePending(
        ok({
          pending: {
            operation_id: OP,
            plan_digest: DIGEST,
            original_context: context,
            harness_id: "codex",
            custody: { state: "prepared" },
            [field]: malformed,
          },
        }),
      ),
    ).toBeNull();
  }
  expect(
    nativePending(
      ok({
        pending: {
          operation_id: OP,
          plan_digest: DIGEST,
          original_context: context,
          harness_id: "codex",
          custody: { state: malformed },
        },
      }),
    ),
  ).toBeNull();
});

it("opens the exact original status after restart and preserves the no-restart receipt", () => {
  const receipt = {
    operation_id: OP,
    review_digest: DIGEST,
    original_context: context,
    harness_id: "codex",
    restart_required: false,
  };
  const response = ok({
    operation_id: OP,
    review_digest: DIGEST,
    original_context: context,
    state: "configured",
    receipt,
  });
  const malformed = JSON.parse('{"toString":"not callable"}') as unknown;
  for (const field of ["operation_id", "review_digest", "state"]) {
    expect(
      nativeStatus(ok({ ...response.data, [field]: malformed })),
    ).toBeNull();
  }
  const original = nativeStatus(response);
  expect(original?.context).toBe(A);
  expect(original?.restartRequired).toBe(false);
  expect(confirmationCommand(required(original), "linux")).toContain(
    "'/original state'",
  );
  expect(
    nativeStatus(
      ok({
        ...response.data,
        receipt: { ...receipt, operation_id: "operation_other" },
      }),
    ),
  ).toBeNull();
});
it("takes an exact catalog selection into native adoption review", async () => {
  vi.mocked(transport.cmdNativeConfigurationPlan).mockResolvedValue(reviewed);
  render(
    <MemoryRouter
      initialEntries={[
        "/targets?setup=setup_selected&version=2.0&digest=" +
          DIGEST +
          "&harness=codex",
      ]}
    >
      <TargetsPage />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("Global configuration folder"), {
    target: { value: "/fixture/config" },
  });
  fireEvent.change(screen.getByLabelText("Change"), {
    target: { value: "adopt" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Review setup" }));
  await waitFor(() =>
    expect(transport.cmdNativeConfigurationPlan).toHaveBeenCalledWith(
      A,
      expect.objectContaining({
        setup: {
          stable_id: "setup_selected",
          version: "2.0",
          passport_digest: DIGEST,
        },
        operation: "adopt",
      }),
    ),
  );
});

it("retains the original source context and controller state for missing-folder retirement", () => {
  const source = "operation_01ARZ3NDEKTSV4RRFFQ69G5FAW";
  const metadata = {
    ...plan,
    native_plan: null,
    missing_retirement: {
      format: "ai-stp-native-missing-target-retirement/1",
      source_operation: source,
      original_plan: { ...plan.native_plan, operation_id: source },
      controller: {
        path: {
          display: "normalized controller",
          utf8_base64: btoa("/original controller"),
        },
      },
    },
  };
  const operation = nativeReview(ok({ plan: metadata, plan_digest: DIGEST }));
  expect(operation?.metadataOnly).toBe(true);
  expect(operation?.context).toBe(A);
  expect(operation?.stateParent).toBe("/original controller");
  expect(operation?.operation).toBe(OP);
});
