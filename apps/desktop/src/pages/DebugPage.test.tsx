// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import DebugPage from "./DebugPage";
import { cmdDebugInfo } from "../transport";
import { useDebug } from "../store";

vi.mock("../transport", () => ({
  cmdDebugInfo: vi.fn(),
  cmdRunRead: vi.fn(),
}));

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  useDebug.setState({ log: [], debugMode: false });
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", originalClipboard);
  } else {
    Reflect.deleteProperty(navigator, "clipboard");
  }
});

it("copies only diagnostic metadata even when local traces contain private payloads", async () => {
  const writeText = vi.fn(async (_text: string) => {});
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  vi.mocked(cmdDebugInfo).mockResolvedValue({
    ok: true,
    data: {
      app_version: "0.1.4",
      platform: "linux",
      arch: "x86_64",
      cli_found: true,
      cli_source: "bundled",
      cli_path: "/canary/private/cli",
      bundled_checked: "/canary/private/resources",
      error: "canary-private-environment-error",
      future_field: "canary-private-future-field",
    },
    warnings: [],
    continuations: [],
    error: null,
    error_code: null,
  });
  useDebug.setState({
    log: Array.from({ length: 55 }, (_, id) => ({
      id,
      ts: 1700000000000 + id,
      cmd: "cli_run_read",
      ms: 12,
      ok: false,
      error_code: "AI_STP_PRECONDITION_FAILED",
      error: "canary-private-error",
      args: { path: "component show", values: { name: "canary-private-name" } },
      result: {
        ok: false,
        data: { root: "/canary/private/project" },
        warnings: ["canary-private-warning"],
        continuations: [],
        error: "canary-private-result-error",
        error_code: "AI_STP_PRECONDITION_FAILED",
      },
    })),
  });
  render(<DebugPage />);
  await screen.findByText(/canary-private-environment-error/);
  fireEvent.click(screen.getByRole("button", { name: "Copy report" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const text = writeText.mock.calls[0][0];
  expect(text).not.toContain("canary");
  const report = JSON.parse(text);
  expect(report.environment).toEqual({
    app_version: "0.1.4",
    platform: "linux",
    arch: "x86_64",
    cli_found: true,
    cli_source: "bundled",
  });
  expect(report.ipc_log).toHaveLength(50);
  expect(report.ipc_log[0]).toEqual({
    ts: 1700000000000,
    cmd: "cli_run_read",
    ms: 12,
    ok: false,
    error_code: "AI_STP_PRECONDITION_FAILED",
  });
  // Export minimization does not silently remove the original local inspection.
  expect(useDebug.getState().log[0].args.values).toEqual({
    name: "canary-private-name",
  });
});
