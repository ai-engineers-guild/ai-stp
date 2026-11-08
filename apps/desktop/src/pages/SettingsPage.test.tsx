// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { invoke } from "@tauri-apps/api/core";
import { useApp } from "../store";
import SettingsPage from "./SettingsPage";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: () => false,
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("shows an unavailable workspace after native IPC fails and keeps preferences reachable", async () => {
  vi.mocked(invoke).mockRejectedValue(new Error("Native IPC unavailable"));
  await act(async () => {
    await useApp.getState().refreshCli();
  });
  render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
  await screen.findByText("Could not communicate with the local engine");
  expect(screen.queryByText("Resolving location…")).toBeNull();
  expect(screen.queryByText("Setup needed")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Initialize workspace" }),
  ).toBeNull();
  expect(screen.getByRole("combobox", { name: "Language" })).toBeTruthy();
});
