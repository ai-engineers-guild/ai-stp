// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router";
import CatalogPage from "./pages/CatalogPage";
import RegistryPage from "./pages/RegistryPage";
import InstallPage from "./pages/InstallPage";
import TasksPage from "./pages/TasksPage";
import AuthPage from "./pages/AuthPage";
import ProfilesPage from "./pages/ProfilesPage";
import { ResultMeta } from "./components/Result";
import { useApp } from "./store";
import { useTaskStart } from "./taskStart";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cmdMachineHelp: vi.fn(),
  cmdCatalogSearch: vi.fn(),
  cmdCatalogShow: vi.fn(),
  cmdTaskIntents: vi.fn(),
  cmdRunRead: vi.fn(),
  cmdTaskStart: vi.fn(),
  cmdTaskStatus: vi.fn(),
  cmdTaskList: vi.fn(),
  cmdTaskAnswer: vi.fn(),
  cmdAuthComplete: vi.fn(),
  cmdAuthLogin: vi.fn(),
  cmdAuthStatus: vi.fn(),
  cmdAuthLogout: vi.fn(),
  cmdProfileApply: vi.fn(),
  cliPlan: vi.fn(),
  cliApplyConfirmed: vi.fn(),
}));
vi.mock("./components/CheckoutOperations", () => ({ default: () => null }));
const ok = (data: Record<string, unknown> = {}): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  continuations: [],
  warnings: [],
});
const command = (
  path: string[],
  mutability: string,
  parameters: unknown[] = [],
) => ({ path, mutability, parameters, summary: "Native operation" });
const help = ok({
  commands: [
    command(["registry", "search"], "read", [
      { name: "kind", choices: ["setup", "component"] },
    ]),
    command(["account", "plan"], "plan", [
      { name: "provider", choices: ["github"] },
    ]),
    command(["local", "apply"], "apply", [
      { name: "plan-digest", required: true },
    ]),
  ],
});
const task = (revision: number) => ({
  task_id: "task_retained",
  revision,
  state: "blocked",
  intent: "author",
  questions: [
    { question_id: "name", prompt: "Component name", actor: "human" },
  ],
});
function mount(element: React.ReactNode, route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]}>{element}</MemoryRouter>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  useTaskStart.getState().reset();
  useApp.setState({
    capabilities: ok({ os: "linux", configuration_installation: "supported" }),
    auth: { session: { state: "absent" } },
    authResult: ok(),
    refreshAuth: vi.fn(async () => {}),
    refreshCli: vi.fn(async () => {}),
  });
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(help);
  vi.mocked(transport.cmdTaskIntents).mockResolvedValue(
    ok({
      intents: [
        { name: "author", when: "Create from files" },
        { name: "install", when: "Install a setup" },
      ],
    }),
  );
  vi.mocked(transport.cmdRunRead).mockResolvedValue(ok({ properties: {} }));
});
afterEach(cleanup);

it("keeps a named account reply and sign-in action fenced to its connection", async () => {
  const first = "connection_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    second = "connection_01ARZ3NDEKTSV4RRFFQ69G5FAW";
  let oldReply!: (result: CmdResult) => void;
  vi.mocked(transport.cmdAuthStatus).mockImplementation(async (connection) =>
    connection === first
      ? new Promise((resolve) => {
          oldReply = resolve;
        })
      : ok({
          connection_id: second,
          origin: "https://company.example.test",
          provider: "keycloak",
          session: { state: "absent" },
        }),
  );
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(
    ok({
      commands: [
        command(["account", "plan"], "plan", [
          { name: "provider", choices: ["github", "keycloak"] },
        ]),
      ],
    }),
  );
  vi.mocked(transport.cmdRunRead).mockImplementation(async (_path, values) =>
    ok({ origin: values?.["api-url"], providers: ["github", "keycloak"] }),
  );
  vi.mocked(transport.cmdAuthLogin).mockResolvedValue(ok());
  function Journey() {
    const navigate = useNavigate();
    return (
      <>
        <button onClick={() => navigate(`/auth?connection=${second}`)}>
          Choose company session
        </button>
        <AuthPage />
      </>
    );
  }
  mount(<Journey />, `/auth?connection=${first}`);
  await waitFor(() =>
    expect(transport.cmdAuthStatus).toHaveBeenCalledWith(first),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Choose company session" }),
  );
  await screen.findByRole("button", { name: "Keycloak" });
  await act(async () =>
    oldReply(
      ok({
        connection_id: first,
        origin: "https://previous.example.test",
        provider: "github",
        session: { state: "authorized", account_id: "old-account" },
      }),
    ),
  );
  expect(screen.queryByText("old-account")).toBeNull();
  expect(screen.queryByRole("button", { name: "GitHub" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Start sign-in" }));
  await waitFor(() =>
    expect(transport.cmdAuthLogin).toHaveBeenCalledWith(
      "keycloak",
      "https://company.example.test",
      second,
    ),
  );
  expect(useApp.getState().auth?.session).toEqual({ state: "absent" });
});

it("discards a previous account response even after returning to the same connection", async () => {
  const first = "connection_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    second = "connection_01ARZ3NDEKTSV4RRFFQ69G5FAW";
  let oldReply!: (result: CmdResult) => void;
  let calls = 0;
  vi.mocked(transport.cmdAuthStatus).mockImplementation(async (connection) => {
    if (connection === first && calls++ === 0)
      return new Promise((resolve) => {
        oldReply = resolve;
      });
    return ok({
      origin: "https://company.example.test",
      provider: "github",
      session: {
        state: "authorized",
        account_id:
          connection === first ? "current-personal" : "current-company",
      },
    });
  });
  function Journey() {
    const navigate = useNavigate();
    return (
      <>
        <button onClick={() => navigate(`/auth?connection=${second}`)}>
          Company view
        </button>
        <button onClick={() => navigate(`/auth?connection=${first}`)}>
          Personal view
        </button>
        <AuthPage />
      </>
    );
  }
  mount(<Journey />, `/auth?connection=${first}`);
  await waitFor(() =>
    expect(transport.cmdAuthStatus).toHaveBeenCalledWith(first),
  );
  fireEvent.click(screen.getByRole("button", { name: "Company view" }));
  await screen.findByText("current-company");
  fireEvent.click(screen.getByRole("button", { name: "Personal view" }));
  await screen.findByText("current-personal");
  await act(async () =>
    oldReply(
      ok({
        origin: "https://old.example.test",
        provider: "github",
        session: { state: "authorized", account_id: "previous-personal" },
      }),
    ),
  );
  expect(screen.queryByText("previous-personal")).toBeNull();
  expect(screen.getByText("current-personal")).toBeTruthy();
});

it("plans a context from the existing account without creating a new enrollment", async () => {
  const organization = "organization_01ARZ3NDEKTSV4RRFFQ69G5FAV";
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) =>
    path === "account organizations"
      ? ok({
          organizations: {
            schema_version: 1,
            items: [
              {
                organization_id: organization,
                kind: "personal",
                display_name: "Personal",
              },
            ],
          },
        })
      : path === "context list"
        ? ok({ contexts: [], selected: null })
        : ok({ connections: [] }),
  );
  vi.mocked(transport.cliPlan).mockResolvedValue(
    ok({ plan: { schema_version: 1 }, plan_digest: "sha256:legacy" }),
  );
  mount(<ProfilesPage />);
  fireEvent.change(screen.getByLabelText("Context connection"), {
    target: { value: "legacy-account" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Read available organizations" }),
  );
  await screen.findByLabelText("Organization");
  expect(transport.cmdRunRead).toHaveBeenCalledWith(
    "account organizations",
    {},
    ["legacy-account"],
  );
  fireEvent.change(screen.getByLabelText("Organization"), {
    target: { value: organization },
  });
  fireEvent.change(screen.getByLabelText("Context label"), {
    target: { value: "Existing personal" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Review context creation" }),
  );
  await waitFor(() =>
    expect(transport.cliPlan).toHaveBeenCalledWith(
      "context create plan",
      { label: "Existing personal", organization },
      ["legacy-account"],
    ),
  );
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
});

it("reviews an exact enrollment plan and requires confirmation before applying", async () => {
  const plan = {
    schema_version: 1,
    operation_id: "operation_reviewed",
    registry_schema_before: 53,
    registry_schema_after: 55,
  };
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(
    ok({
      commands: [
        command(["account", "connections", "plan"], "plan", [
          { name: "provider", choices: ["github"] },
        ]),
      ],
    }),
  );
  vi.mocked(transport.cmdRunRead).mockImplementation(async (path) =>
    path === "account providers"
      ? ok({ origin: "https://chosen.example.test", providers: ["github"] })
      : path === "context list"
        ? ok({ contexts: [], selected: null })
        : ok({ connections: [] }),
  );
  vi.mocked(transport.cliPlan).mockResolvedValue(
    ok({ plan, plan_digest: "sha256:reviewed" }),
  );
  vi.mocked(transport.cmdProfileApply).mockResolvedValue(ok());
  mount(<ProfilesPage />);
  fireEvent.change(screen.getByLabelText("Connection label"), {
    target: { value: "Personal" },
  });
  fireEvent.change(screen.getByLabelText("Server origin"), {
    target: { value: "https://chosen.example.test" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Check server sign-in methods" }),
  );
  await screen.findByLabelText("Sign-in method");
  fireEvent.click(
    screen.getByRole("button", { name: "Review connection creation" }),
  );
  await screen.findByText("sha256:reviewed");
  const apply = screen.getByRole("button", {
    name: "Apply reviewed change",
  }) as HTMLButtonElement;
  expect(apply.disabled).toBe(true);
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(apply);
  await waitFor(() =>
    expect(transport.cmdProfileApply).toHaveBeenCalledWith(
      "account connections apply",
      plan,
      "sha256:reviewed",
      true,
    ),
  );
});

it("offers only sign-in methods configured at the chosen origin", async () => {
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(
    ok({
      commands: [
        command(["account", "plan"], "plan", [
          { name: "provider", choices: ["github", "keycloak"] },
        ]),
      ],
    }),
  );
  vi.mocked(transport.cmdRunRead).mockResolvedValue(
    ok({ origin: "https://selected.example.test", providers: ["keycloak"] }),
  );
  vi.mocked(transport.cmdAuthLogin).mockResolvedValue(ok());
  mount(<AuthPage />);
  await screen.findByRole("button", { name: "Keycloak" });
  expect(screen.queryByRole("button", { name: "GitHub" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Start sign-in" }));
  await waitFor(() =>
    expect(transport.cmdAuthLogin).toHaveBeenCalledWith(
      "keycloak",
      "https://selected.example.test",
    ),
  );
});

it("keeps sign-in unavailable when discovery fails and retries explicitly", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue({
    ...ok(),
    ok: false,
    error: "Unavailable",
  });
  mount(<AuthPage />);
  await screen.findByRole("button", { name: "Retry sign-in methods" });
  expect(
    (screen.getByRole("button", { name: "Start sign-in" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  vi.mocked(transport.cmdRunRead).mockResolvedValue(
    ok({ origin: "https://selected.example.test", providers: ["github"] }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Retry sign-in methods" }),
  );
  await screen.findByRole("button", { name: "GitHub" });
  expect(
    (screen.getByRole("button", { name: "Start sign-in" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});

it("discards provider discovery from an origin that is no longer selected", async () => {
  let previous!: (value: CmdResult) => void;
  useApp.setState({
    auth: {
      origin: "https://previous.example.test",
      session: { state: "absent" },
    },
  });
  vi.mocked(transport.cmdRunRead).mockImplementation(async (_path, values) => {
    if (values?.["api-url"] === "https://previous.example.test") {
      return new Promise((resolve) => {
        previous = resolve;
      });
    }
    return ok({ providers: [] });
  });
  mount(<AuthPage />);
  await act(async () => {
    useApp.setState({
      auth: {
        origin: "https://current.example.test",
        session: { state: "absent" },
      },
    });
  });
  await screen.findByText(
    "This server has no sign-in methods supported by this engine.",
  );
  await act(async () => previous(ok({ providers: ["github"] })));
  expect(screen.queryByRole("button", { name: "GitHub" })).toBeNull();
  expect(
    (screen.getByRole("button", { name: "Start sign-in" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});

it("discards a catalog page when its filter changes while the request is in flight", async () => {
  let complete!: (value: CmdResult) => void;
  vi.mocked(transport.cmdCatalogSearch).mockReturnValue(
    new Promise((resolve) => {
      complete = resolve;
    }),
  );
  mount(<CatalogPage />);
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Search catalog",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "Search catalog" }));
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "component" },
  });
  complete(
    ok({
      items: [{ stable_id: "setup_old", latest_name: "Stale setup" }],
      next_cursor: "old-cursor",
    }),
  );
  await waitFor(() => expect(screen.queryByText("Stale setup")).toBeNull());
  expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  expect(transport.cmdCatalogSearch).toHaveBeenCalledWith(
    "setup",
    "",
    false,
    undefined,
  );
});

it("revokes apply confirmation when inputs change and sends the exact reviewed digest", async () => {
  vi.mocked(transport.cliApplyConfirmed).mockResolvedValue(ok());
  mount(<RegistryPage />);
  fireEvent.click(await screen.findByRole("button", { name: /local apply/ }));
  const digest = screen.getByRole("textbox", { name: /plan-digest/ });
  fireEvent.change(digest, { target: { value: "sha256:first" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.change(digest, { target: { value: "sha256:reviewed" } });
  expect(
    (
      screen.getByRole("button", {
        name: "Apply operation",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Apply operation" }));
  await waitFor(() =>
    expect(transport.cliApplyConfirmed).toHaveBeenCalledWith(
      "local apply",
      { "plan-digest": "sha256:reviewed" },
      [],
      true,
      {},
    ),
  );
});

it("recovers the task retained by a failed start and answers using its current revision", async () => {
  vi.mocked(transport.cmdTaskStart).mockResolvedValue({
    ...ok(),
    ok: false,
    error: "Interrupted",
    error_code: "AI_STP_PRECONDITION_FAILED",
    error_details: { task_id: "task_retained" },
  });
  vi.mocked(transport.cmdTaskStatus).mockResolvedValue(ok(task(7)));
  vi.mocked(transport.cmdTaskAnswer).mockResolvedValue(ok(task(8)));
  mount(<InstallPage />, "/install?intent=author");
  fireEvent.click(await screen.findByRole("checkbox"));
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Start authoring",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "Start authoring" }));
  fireEvent.change(
    await screen.findByRole("textbox", { name: "Component name" }),
    { target: { value: "Reviewed name" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
  await waitFor(() =>
    expect(transport.cmdTaskAnswer).toHaveBeenCalledWith(
      "task_retained",
      "7",
      "name",
      "Reviewed name",
    ),
  );
});

it("retains one start identity across uncertain retries and creates a new one only for a new request", async () => {
  vi.mocked(transport.cmdTaskStart).mockResolvedValue({
    ...ok(),
    ok: false,
    error_code: "AI_STP_TIMEOUT_UNCONFIRMED",
    error: "Inspect before retrying",
  });
  const request = { intent: "author" };
  await useTaskStart.getState().start(request);
  await useTaskStart.getState().start(request);
  const calls = vi.mocked(transport.cmdTaskStart).mock.calls;
  expect(calls[0][1]).toBe(calls[1][1]);
  expect(calls[0][1]?.length).toBeGreaterThanOrEqual(16);
  useTaskStart.getState().reset();
  await useTaskStart.getState().start(request);
  expect(calls[2][1]).not.toBe(calls[0][1]);
});

it("shows the native platform refusal before installation while keeping authoring available", async () => {
  useApp.setState({
    capabilities: ok({
      os: "windows",
      configuration_installation: "unavailable",
    }),
  });
  mount(<InstallPage />, "/install");
  expect(
    await screen.findByText(/Setup installation is unavailable on windows/),
  ).toBeTruthy();
  expect(
    (
      screen.getByRole("button", {
        name: "Start installation",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.click(
    await screen.findByRole("button", { name: "Create from files" }),
  );
  expect(screen.queryByText(/Setup installation is unavailable/)).toBeNull();
  expect(screen.getByRole("button", { name: "Start authoring" })).toBeTruthy();
});

it("does not open or poll an expired device code", async () => {
  useApp.setState({
    auth: {
      session: {
        state: "pending",
        user_code: "OLD-CODE",
        expires_at: "2000-01-01T00:00:00Z",
        verification_uri: "https://example.com/verify",
      },
    },
  });
  mount(<AuthPage />);
  expect(await screen.findByText(/This code has expired/)).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Open browser and confirm" }),
  ).toBeNull();
  expect(transport.cmdAuthComplete).not.toHaveBeenCalled();
});

it("does not replace a new catalog selection with the result of an already opened task", async () => {
  vi.mocked(transport.cmdTaskStart).mockResolvedValue(
    ok({ ...task(13), state: "completed", questions: [] }),
  );
  await useTaskStart.getState().start({ intent: "author" });
  useTaskStart.getState().acknowledge();
  mount(
    <InstallPage />,
    "/install?setup=setup_selected&version=1.0&digest=sha256:reviewed&harness=codex",
  );
  await screen.findByRole("button", { name: "Start installation" });
  expect(transport.cmdTaskStatus).not.toHaveBeenCalled();
  expect(useTaskStart.getState().key).toBeNull();
});

it("does not apply a manual task read after leaving and returning to the same task", async () => {
  let late!: (result: CmdResult) => void;
  let reads = 0;
  vi.mocked(transport.cmdTaskStatus).mockImplementation(async (id) => {
    if (id !== "task_retained") return ok({ ...task(2), task_id: id });
    reads++;
    if (reads === 2) return new Promise((resolve) => { late = resolve; });
    return ok(task(reads === 1 ? 1 : 9));
  });
  function Journey() {
    const navigate = useNavigate();
    return <><button onClick={() => navigate("/install?task=task_other")}>Other task</button>
      <button onClick={() => navigate("/install?task=task_retained")}>Original task</button><InstallPage /></>;
  }
  mount(<Journey />, "/install?task=task_retained");
  await screen.findByText("Revision 1");
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() => expect(transport.cmdTaskStatus).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole("button", { name: "Other task" }));
  await screen.findByText("Revision 2");
  fireEvent.click(screen.getByRole("button", { name: "Original task" }));
  await screen.findByText("Revision 9");
  await act(async () => late(ok(task(3))));
  expect(screen.getByText("Revision 9")).toBeTruthy();
  expect(screen.queryByText("Revision 3")).toBeNull();
});

it("does not let an old task mutation clear a later visit's pending read", async () => {
  let finishAction!: (result: CmdResult) => void;
  let finishRead!: (result: CmdResult) => void;
  let reads = 0;
  vi.mocked(transport.cmdTaskAnswer).mockReturnValue(new Promise((resolve) => { finishAction = resolve; }));
  vi.mocked(transport.cmdTaskStatus).mockImplementation(async (id) => {
    if (id !== "task_retained") return ok({ ...task(2), task_id: id });
    reads++;
    if (reads === 2) return new Promise((resolve) => { finishRead = resolve; });
    return ok(task(reads === 1 ? 1 : 9));
  });
  function Journey() {
    const navigate = useNavigate();
    return <><button onClick={() => navigate("/install?task=task_other")}>Other task</button>
      <button onClick={() => navigate("/install?task=task_retained")}>Original task</button><InstallPage /></>;
  }
  mount(<Journey />, "/install?task=task_retained");
  fireEvent.change(await screen.findByRole("textbox", { name: "Component name" }), { target: { value: "Original answer" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
  await waitFor(() => expect(transport.cmdTaskAnswer).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Other task" }));
  await screen.findByText("Revision 2");
  fireEvent.click(screen.getByRole("button", { name: "Original task" }));
  await waitFor(() => expect(transport.cmdTaskStatus).toHaveBeenCalledTimes(3));
  try {
    await act(async () => finishAction(ok(task(3))));
    expect(transport.cmdTaskStatus).toHaveBeenCalledTimes(3);
    expect(screen.getByText("Reading the latest task state")).toBeTruthy();
    expect(screen.queryByText("Revision 3")).toBeNull();
  } finally {
    await act(async () => finishRead(ok(task(9))));
  }
  await screen.findByText("Revision 9");
});

it.each([
  { ...task(1), task_id: "task_unrequested" },
  { ...task(1), ownership: { kind: "corporate", organization_id: "untrusted" } },
  { ...task(1), ownership: { kind: "personal", native_account_id: "invalid", native_device_id: "invalid" } },
])("refuses a mismatched or unsupported native task reply", async (value) => {
  vi.mocked(transport.cmdTaskStatus).mockResolvedValue(ok(value));
  mount(<InstallPage />, "/install?task=task_retained");
  await screen.findByText("The engine reply does not describe the requested task and supported ownership.");
  expect(screen.queryByRole("button", { name: "Submit answer" })).toBeNull();
  expect(transport.cmdTaskAnswer).not.toHaveBeenCalled();
});

it("shows the original personal task owner reported by the native journal", async () => {
  const ownership = { kind: "personal", native_account_id: "account_01ARZ3NDEKTSV4RRFFQ69G5FAV", native_device_id: "device_01ARZ3NDEKTSV4RRFFQ69G5FAW" };
  vi.mocked(transport.cmdTaskStatus).mockResolvedValue(ok({ ...task(7), ownership }));
  mount(<InstallPage />, "/install?task=task_retained");
  await screen.findByText("Personal task · retained local owner");
  expect(screen.getByText(ownership.native_account_id)).toBeTruthy();
  expect(screen.getByText(ownership.native_device_id)).toBeTruthy();
});

it("keeps a refreshed Activity list when the initial read completes later", async () => {
  let initial!: (result: CmdResult) => void;
  vi.mocked(transport.cmdTaskList).mockReturnValueOnce(new Promise((resolve) => { initial = resolve; }))
    .mockResolvedValueOnce(ok({ tasks: [{ task_id: "task_new", intent: "author", state: "blocked" }] }));
  mount(<TasksPage />);
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByText("task_new");
  await act(async () => initial(ok({ tasks: [{ task_id: "task_old", intent: "author", state: "blocked" }] })));
  expect(screen.getByText("task_new")).toBeTruthy();
  expect(screen.queryByText("task_old")).toBeNull();
});

it("offers manual context review for the native historical-identity refusal without starting a mutation", () => {
  mount(<ResultMeta r={{ ...ok(), ok: false, error_code: "AI_STP_PRECONDITION_FAILED",
    error: "Review a fresh context using the existing sign-in.",
    error_details: { reason: "historical_native_identity", next_action: "review_current_context" } }} />);
  expect(screen.getByRole("link", { name: "Review current context" }).getAttribute("href")).toBe("/profiles");
  expect(transport.cliPlan).not.toHaveBeenCalled();
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
  expect(transport.cmdAuthLogin).not.toHaveBeenCalled();
});

it.each([
  ["AI_STP_PRECONDITION_FAILED", "changed_membership"],
  ["AI_STP_DEPENDENCY_UNAVAILABLE", "historical_native_identity"],
  ["AI_STP_PRECONDITION_FAILED", null],
])("does not infer context recovery from unrelated failure %s/%s", (code, reason) => {
  mount(<ResultMeta r={{ ...ok(), ok: false, error_code: code,
    error: "historical_native_identity appears only in error prose",
    error_details: { reason } }} />);
  expect(screen.queryByRole("link", { name: "Review current context" })).toBeNull();
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
});
