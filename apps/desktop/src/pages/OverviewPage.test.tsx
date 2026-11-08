// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import OverviewPage from "./OverviewPage";
import { useApp } from "../store";
import { useContexts } from "../contexts";
import type { CmdResult } from "../transport";

const ok = (data: Record<string, unknown>): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
afterEach(cleanup);
function open({
  engine = true,
  identity = true,
  context = true,
  installation = true,
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
