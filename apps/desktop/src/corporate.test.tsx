// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import CorporatePage from "./pages/CorporatePage";
import { useContexts, type ContextView } from "./contexts";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cmdMachineHelp: vi.fn(),
  cmdRunRead: vi.fn(),
  cliPlan: vi.fn(),
  cmdProfileApply: vi.fn(),
}));
const A: ContextView = {
  id: "context_A",
  label: "First",
  mode: "corporate",
  organization: "First company",
  origin: "https://first.example.test",
  connection: "connection_A",
};
const B: ContextView = {
  ...A,
  id: "context_B",
  label: "Second",
  organization: "Second company",
  origin: "https://second.example.test",
  connection: "connection_B",
};
const HARNESSES = [
  "codex",
  "claude-code",
  "antigravity",
  "grok-build",
  "cursor",
  "opencode",
  "pi",
];
const ok = (data: Record<string, unknown>): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
const reply = (id: string, name: string) =>
  ok({
    observation_digest: "sha256:fixture",
    observation: {
      context: { context_id: id },
      data: { items: [{ project_id: "remote_project_fixture", name }] },
      observation: {
        capabilities: { generated_at: "now", expires_at: "later" },
      },
    },
  });
beforeEach(() => {
  vi.clearAllMocks();
  useContexts.setState({
    views: [A, B],
    selected: A,
    loading: false,
    switching: false,
  });
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(
    ok({
      commands: [
        {
          path: ["corporate", "assignments", "preview"],
          mutability: "plan",
          parameters: [{ name: "harness", choices: HARNESSES }],
        },
      ],
    }),
  );
});
afterEach(cleanup);
function mount() {
  render(
    <MemoryRouter>
      <CorporatePage />
    </MemoryRouter>,
  );
}
async function ready() {
  await waitFor(() =>
    expect(
      screen
        .getByRole("button", { name: "Read projects" })
        .hasAttribute("disabled"),
    ).toBe(false),
  );
}

it("uses the explicit view and selected project for a read-only seven-harness preview", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue(reply(A.id, "Our project"));
  vi.mocked(transport.cliPlan).mockResolvedValue(reply(A.id, "Assigned setup"));
  mount();
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Read projects" }));
  await screen.findByText("Our project");
  expect(transport.cmdRunRead).toHaveBeenCalledWith(
    "corporate projects",
    { context: A.id },
    ["membership-only"],
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Preview this project's assignments" }),
  );
  const harness = screen.getByLabelText("Harness");
  expect(within(harness).getAllByRole("option").length).toBe(7);
  fireEvent.change(harness, { target: { value: "grok-build" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview assignments" }));
  await waitFor(() =>
    expect(transport.cliPlan).toHaveBeenCalledWith(
      "corporate assignments preview",
      {
        context: A.id,
        harness: "grok-build",
        project: "remote_project_fixture",
      },
    ),
  );
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /apply/i })).toBe(null);
});

it("discards an old company response after A to B to A selection", async () => {
  let finish!: (result: CmdResult) => void;
  vi.mocked(transport.cmdRunRead)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce(reply(A.id, "Current project"));
  mount();
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Read projects" }));
  act(() => useContexts.setState({ selected: B }));
  act(() => useContexts.setState({ selected: A }));
  fireEvent.click(screen.getByRole("button", { name: "Read projects" }));
  await screen.findByText("Current project");
  await act(async () => {
    finish(reply(A.id, "Stale project"));
  });
  expect(screen.queryByText("Stale project")).toBe(null);
  expect(screen.getByText("Current project")).toBeTruthy();
});

it("refuses a response from another context before rendering its data", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue({
    ...reply(B.id, "Other company project"),
    warnings: ["Other company warning"],
  });
  mount();
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Read projects" }));
  await screen.findByRole("alert");
  expect(screen.queryByText("Other company project")).toBe(null);
  expect(screen.queryByText("Other company warning")).toBe(null);
});

it("keeps personal operation free of company reads", async () => {
  useContexts.setState({
    selected: {
      ...A,
      mode: "personal",
      organization: null,
      origin: null,
      connection: null,
    },
  });
  mount();
  await screen.findByText("Select a corporate context");
  expect(transport.cmdRunRead).not.toHaveBeenCalled();
  expect(transport.cliPlan).not.toHaveBeenCalled();
});

it("reads the next organization catalog page with its original search and harness filters", async () => {
  const page = (name: string, cursor: string | null) =>
    ok({
      observation: {
        context: { context_id: A.id },
        request: { action: "catalog" },
        data: {
          items: [
            {
              stable_id: "setup_fixture",
              latest_name: name,
              latest_version: "2.4",
              latest_description: "Company setup details",
              latest_lifecycle: "active",
            },
          ],
          page: { next_cursor: cursor },
        },
      },
    });
  vi.mocked(transport.cmdRunRead)
    .mockResolvedValueOnce(page("First setup", "opaque-page-cursor"))
    .mockResolvedValueOnce(page("Next setup", null));
  mount();
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "Catalog" }));
  fireEvent.change(screen.getByLabelText("Search"), {
    target: { value: "project setup" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Read catalog" }));
  await screen.findByText("First setup");
  expect(screen.getByText("active · 2.4")).toBeTruthy();
  expect(screen.getByText("Company setup details")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Read next page" }));
  await screen.findByText("Next setup");
  expect(transport.cmdRunRead).toHaveBeenLastCalledWith(
    "corporate catalog search",
    {
      context: A.id,
      kind: "setup",
      query: "project setup",
      harness: "codex",
      cursor: "opaque-page-cursor",
    },
    [],
  );
  expect(screen.queryByRole("button", { name: "Read next page" })).toBe(null);
});
