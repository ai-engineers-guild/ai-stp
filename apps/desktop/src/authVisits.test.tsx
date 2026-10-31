// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router";
import { openUrl } from "@tauri-apps/plugin-opener";
import AuthPage from "./pages/AuthPage";
import { useApp } from "./store";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
vi.mock("./transport", async (original) => ({
  ...(await original<typeof import("./transport")>()),
  cmdAuthStatus: vi.fn(),
  cmdAuthComplete: vi.fn(),
  cmdMachineHelp: vi.fn(),
  cmdRunRead: vi.fn(),
}));
const A = "connection_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const B = "connection_01ARZ3NDEKTSV4RRFFQ69G5FAW";
const ok = (data: Record<string, unknown> = {}): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
function pending(connection: string) {
  return ok({
    connection_id: connection,
    origin: "https://company.example.test",
    provider: "github",
    session: {
      state: "pending",
      user_code: "TEST-CODE",
      verification_uri_complete:
        "https://company.example.test/verify?code=TEST-CODE",
      expires_at: new Date(Date.now() + 600000).toISOString(),
      next_poll_at: new Date(Date.now() + 30000).toISOString(),
      interval: 30,
    },
  });
}
function Journey() {
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate(`/auth?connection=${A}`)}>
        First account
      </button>
      <button onClick={() => navigate(`/auth?connection=${B}`)}>
        Second account
      </button>
      <AuthPage />
    </>
  );
}
function mount() {
  render(
    <MemoryRouter initialEntries={[`/auth?connection=${A}`]}>
      <Journey />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  useApp.setState({
    auth: null,
    authResult: null,
    refreshAuth: vi.fn(async () => {}),
  });
  vi.mocked(transport.cmdAuthStatus).mockImplementation(async (connection) =>
    pending(connection!),
  );
  vi.mocked(transport.cmdAuthComplete).mockResolvedValue(ok());
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(ok({ commands: [] }));
  vi.mocked(transport.cmdRunRead).mockResolvedValue(ok({ providers: [] }));
});
afterEach(cleanup);

it("keeps the newest status within the same retained account", async () => {
  let finish!: (value: CmdResult) => void;
  vi.mocked(transport.cmdAuthStatus)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce(
      ok({
        origin: "https://company.example.test",
        provider: "github",
        session: { state: "authorized", account_id: "current-account" },
      }),
    );
  mount();
  await waitFor(() => expect(transport.cmdAuthStatus).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await screen.findByText("current-account");
  await act(async () =>
    finish(
      ok({
        origin: "https://company.example.test",
        provider: "github",
        session: { state: "authorized", account_id: "previous-account" },
      }),
    ),
  );
  expect(screen.queryByText("previous-account")).toBeNull();
  expect(screen.getByText("current-account")).toBeTruthy();
});

it("discards an old browser failure after leaving and returning to an account", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(openUrl).mockImplementationOnce(
    () =>
      new Promise((_, fail) => {
        reject = fail;
      }),
  );
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open browser and confirm" }),
  );
  await waitFor(() => expect(openUrl).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Second account" }));
  await waitFor(() => expect(transport.cmdAuthStatus).toHaveBeenCalledWith(B));
  fireEvent.click(screen.getByRole("button", { name: "First account" }));
  await waitFor(() => expect(transport.cmdAuthStatus).toHaveBeenCalledTimes(3));
  await screen.findByRole("button", { name: "Open browser and confirm" });
  await act(async () => reject(new Error("previous browser attempt failed")));
  expect(screen.queryByText(/The browser could not be opened/)).toBeNull();
  expect(transport.cmdAuthComplete).not.toHaveBeenCalled();
});

it("does not revive a stopped approval attempt when opening the browser finishes late", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(openUrl).mockImplementationOnce(
    () =>
      new Promise((_, fail) => {
        reject = fail;
      }),
  );
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open browser and confirm" }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Stop waiting" }));
  await act(async () => reject(new Error("stopped browser attempt failed")));
  expect(screen.queryByText(/The browser could not be opened/)).toBeNull();
  expect(transport.cmdAuthComplete).not.toHaveBeenCalled();
  expect(transport.cmdAuthStatus).toHaveBeenCalledTimes(1);
  expect(
    screen
      .getByRole("button", { name: "Open browser and confirm" })
      .hasAttribute("disabled"),
  ).toBe(false);
});

it("does not show a previous connection's browser failure in a new account view", async () => {
  vi.mocked(openUrl).mockRejectedValueOnce(
    new Error("first connection browser failed"),
  );
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open browser and confirm" }),
  );
  await screen.findByText(/The browser could not be opened/);
  fireEvent.click(screen.getByRole("button", { name: "Second account" }));
  await waitFor(() => expect(transport.cmdAuthStatus).toHaveBeenCalledWith(B));
  expect(screen.queryByText(/The browser could not be opened/)).toBeNull();
  expect(transport.cmdAuthComplete).not.toHaveBeenCalled();
});

it("keeps a new approval attempt active when an earlier stopped browser request rejects", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(openUrl)
    .mockImplementationOnce(
      () =>
        new Promise((_, fail) => {
          reject = fail;
        }),
    )
    .mockResolvedValueOnce();
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open browser and confirm" }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Stop waiting" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Open browser and confirm" }),
  );
  await waitFor(() => expect(openUrl).toHaveBeenCalledTimes(2));
  await act(async () =>
    reject(new Error("old stopped browser request failed")),
  );
  expect(screen.queryByText(/The browser could not be opened/)).toBeNull();
  expect(screen.getByRole("button", { name: "Stop waiting" })).toBeTruthy();
  expect(transport.cmdAuthComplete).not.toHaveBeenCalled();
});
