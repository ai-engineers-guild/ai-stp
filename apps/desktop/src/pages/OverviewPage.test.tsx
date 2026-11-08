// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import { MemoryRouter } from "react-router";
import OverviewPage from "./OverviewPage";
import { useApp } from "../store";
import { useContexts } from "../contexts";
import type { CmdResult } from "../transport";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: () => false,
}));

const ok = (data: Record<string, unknown>): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function open({
  engine = true,
  identity = true,
  context = true,
  installation = true,
  contextError = false,
} = {}) {
  useApp.setState({
    cliOk: engine,
    cliVersion: "0.3.0",
    capabilities: ok({ native_configuration: { available: installation } }),
    doctor: ok({
      checks: [
        {
          name: "local_identity",
          state: identity ? "ready" : "missing",
          detail: "",
        },
      ],
    }),
    location: null,
    engineResult: null,
  });
  useContexts.setState({
    loading: false,
    result: contextError
      ? {
          ...ok({}),
          ok: false,
          data: null,
          error: "Context read failed",
          error_code: "CONTEXT_VIEW",
        }
      : null,
    selected: context
      ? {
          id: "context_fixture",
          label: "My workspace",
          mode: "personal",
          organization: null,
          origin: null,
          connection: null,
        }
      : null,
  });
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  );
}
it("shows unsupported configuration as unavailable after a successful capability read", () => {
  open({ installation: false });
  const status = screen.getByText("Setup configuration").parentElement!;
  expect(within(status).getByText("Unavailable")).toBeTruthy();
  expect(within(status).queryByText("Checking…")).toBeNull();
});
it("distinguishes an unreadable workspace list from a workspace that does not exist", () => {
  open({ context: false, contextError: true });
  expect(screen.queryByRole("link", { name: "Create a context" })).toBeNull();
  expect(
    screen.getByRole("link", { name: "Check workspaces" }).getAttribute("href"),
  ).toBe("/profiles");
  expect(screen.getByRole("alert").textContent).toContain(
    "Context read failed",
  );
});
it("refreshes the selected context changed outside the app before offering the next step", async () => {
  const context = "context_01ARZ3NDEKTSV4RRFFQ69G5FAV";
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command === "cli_version") return ok({ version: "0.3.0" });
    if (command === "cli_capabilities")
      return ok({ native_configuration: { available: true } });
    if (command === "cli_doctor")
      return ok({ checks: [{ name: "local_identity", state: "ready" }] });
    if (command === "cli_run_read") {
      const path = (args as { path: string }).path;
      if (path === "state path") return ok({ state_dir: "/fixture/state" });
      if (path === "context list")
        return ok({
          contexts: [
            {
              context: {
                context_id: context,
                label: "Created in CLI",
                authority: { kind: "local" },
              },
            },
          ],
          selected: { context_id: context },
        });
    }
    throw new Error(`Unexpected native call ${command}`);
  });
  open({ context: false });
  expect(
    screen.getByRole("region", { name: "Create your workspace" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByText("Created in CLI")).toBeTruthy();
  expect(
    await screen.findByRole("region", { name: "Choose a setup for your tool" }),
  ).toBeTruthy();
});
it.each([
  [
    { engine: false },
    "Reconnect to the local engine",
    "Open Settings",
    "/settings",
  ],
  [
    { identity: false },
    "Prepare this device",
    "Set up this device",
    "/settings",
  ],
  [
    { context: false },
    "Create your workspace",
    "Create a context",
    "/profiles",
  ],
  [{}, "Choose a setup for your tool", "Find a setup", "/catalog"],
] as const)(
  "offers the next action for %j",
  (state, title, action, destination) => {
    open(state);
    const next = screen.getByRole("region", { name: title });
    expect(
      within(next).getByRole("link", { name: action }).getAttribute("href"),
    ).toBe(destination);
  },
);
