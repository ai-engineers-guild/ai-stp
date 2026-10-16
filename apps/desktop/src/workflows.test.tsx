// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import CatalogPage from "./pages/CatalogPage";
import RegistryPage from "./pages/RegistryPage";
import InstallPage from "./pages/InstallPage";
import AuthPage from "./pages/AuthPage";
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
  cmdTaskAnswer: vi.fn(),
  cmdAuthComplete: vi.fn(),
  cliApplyConfirmed: vi.fn(),
}));
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
