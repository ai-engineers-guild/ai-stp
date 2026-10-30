import { afterEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdProfileApply,
  cmdCheckoutApply,
  cmdBindingRetirementApply,
  cmdMissingBindingRetirementApply,
  cmdCheckoutLocationApply,
  cmdHeartbeatConsentApply,
  cmdRunRead,
  cmdTaskStart,
  cmdVersion,
} from "./transport";
import { useDebug } from "./store";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
afterEach(() => {
  vi.resetAllMocks();
  useDebug.setState({ debugMode: false, log: [] });
});
it("omits the reviewed corporate heartbeat plan and reply from shared diagnostics", async () => {
  useDebug.setState({ debugMode: true });
  vi.mocked(invoke).mockResolvedValue({ ok: true, data: { private: "reply-canary" }, warnings: [], continuations: [], error: null, error_code: null });
  await cmdHeartbeatConsentApply({ private: "plan-canary" }, "sha256:reviewed", true);
  expect(invoke).toHaveBeenCalledWith("profile_apply", {
    path: "corporate heartbeat consent apply", plan: { private: "plan-canary" }, digest: "sha256:reviewed", confirmed: true,
  });
  expect(JSON.stringify(useDebug.getState().log)).not.toMatch(/plan-canary|reply-canary/);
});
it("returns a structured failure when IPC throws synchronously", async () => {
  vi.mocked(invoke).mockImplementation(() => {
    throw new Error("No native bridge");
  });
  expect(await cmdVersion()).toMatchObject({
    ok: false,
    error_code: "IPC_THROW",
  });
});
it("does not retain form content or generic task answers in a diagnostic trace", async () => {
  useDebug.setState({ debugMode: true });
  vi.mocked(invoke).mockResolvedValue({
    ok: true,
    data: {},
    error: null,
    error_code: null,
    warnings: [],
    continuations: [],
  });
  await cmdTaskStart("author", "desktop-test-key-01", undefined, {
    name: "private user input",
  });
  await cliApplyConfirmed(
    "task answer",
    { value: "another private answer" },
    [],
    true,
  );
  const log = JSON.stringify(useDebug.getState().log);
  expect(log).not.toContain("private user input");
  expect(log).not.toContain("another private answer");
  expect(log).toContain("[task input]");
  expect(log).toContain("[user answer]");
});

it("keeps company content out of the shared trace while returning the full reply to its caller", async () => {
  useDebug.setState({ debugMode: true });
  const reply = {
    ok: true,
    data: {
      name: "canary-company-directory",
      root: "/canary/private/repository",
    },
    error: null,
    error_code: null,
    warnings: ["canary-company-warning"],
    continuations: [],
  };
  vi.mocked(invoke).mockResolvedValue(reply);
  expect(
    await cmdRunRead("corporate catalog search", {
      context: "context_fixture",
      query: "canary-company-query",
    }),
  ).toBe(reply);
  await cliPlan("corporate assignments preview", {
    context: "context_fixture",
    project: "canary-company-project",
  });
  await cmdRunRead("context list");
  await cmdProfileApply(
    "context apply",
    { label: "canary-company-label" },
    "sha256:fixture",
    true,
  );
  vi.mocked(invoke).mockResolvedValue({
    ...reply,
    ok: false,
    error: "canary-company-error",
    error_code: "FORBIDDEN",
  });
  expect((await cmdRunRead("corporate teams")).error).toBe(
    "canary-company-error",
  );
  vi.mocked(invoke).mockRejectedValue(new Error("canary-company-transport"));
  expect((await cmdRunRead("corporate projects")).error_code).toBe("IPC_THROW");
  const entries = useDebug.getState().log;
  expect(entries).toHaveLength(6);
  expect(JSON.stringify(entries)).not.toContain("canary");
  expect(entries.every((entry) => entry.result === undefined)).toBe(true);
  expect(entries.some((entry) => entry.error_code === "FORBIDDEN")).toBe(true);
  expect(entries[0].error_code).toBe("IPC_THROW");
});

it("omits enrollment recovery plans and account evidence from the shared trace", async () => {
  useDebug.setState({ debugMode: true });
  const reply = {
    ok: true,
    data: { account_id: "canary-account", root: "/canary/private/state" },
    error: null,
    error_code: null,
    warnings: ["canary-recovery-warning"],
    continuations: [],
  };
  vi.mocked(invoke).mockResolvedValue(reply);
  expect(await cmdRunRead("account connections recovery list")).toBe(reply);
  await cliPlan(" account   connections recovery plan ", {
    connection: "canary-old-connection",
    label: "canary-new-label",
  });
  await cmdProfileApply(
    "account connections recovery apply",
    {
      previous: "canary-original-evidence",
      replacement: "canary-new-key-plan",
    },
    "sha256:fixture",
    true,
  );
  vi.mocked(invoke).mockRejectedValue(new Error("canary-recovery-transport"));
  expect(
    (await cmdRunRead("account connections recovery list")).error_code,
  ).toBe("IPC_THROW");
  const entries = useDebug.getState().log;
  expect(entries).toHaveLength(4);
  expect(JSON.stringify(entries)).not.toContain("canary");
  expect(entries.every((entry) => entry.result === undefined)).toBe(true);
  expect(entries[0].error_code).toBe("IPC_THROW");
});

it("keeps reviewed checkout plans and original outcome replies out of shared diagnostics", async () => {
  useDebug.setState({ debugMode: true });
  const reply = { ok: true, data: { original_actor: "canary-checkout-actor" }, error: null,
    error_code: null, warnings: ["canary-private-warning"], continuations: [] };
  vi.mocked(invoke).mockResolvedValue(reply);
  expect(await cmdCheckoutApply({ snapshot: "canary-private-project" }, "sha256:exact", true, "canary-context", "/canary/git")).toBe(reply);
  expect(invoke).toHaveBeenLastCalledWith("checkout_apply", {
    plan: { snapshot: "canary-private-project" }, digest: "sha256:exact", confirmed: true,
    context: "canary-context", gitExecutable: "/canary/git",
  });
  vi.mocked(invoke).mockRejectedValue(new Error("canary-checkout-transport"));
  expect((await cmdCheckoutApply({}, "sha256:exact", true)).error_code).toBe("IPC_THROW");
  const entries = useDebug.getState().log;
  expect(entries).toHaveLength(2);
  expect(JSON.stringify(entries)).not.toContain("canary");
  expect(entries.every((entry) => entry.result === undefined)).toBe(true);
});

it("routes exact binding retirement through the bounded checkout bridge without shared trace content", async () => {
  useDebug.setState({ debugMode: true });
  const reply = { ok: true, data: { original_actor: "canary-retired-actor" }, error: null,
    error_code: null, warnings: [], continuations: [] };
  vi.mocked(invoke).mockResolvedValue(reply);
  const plan = { snapshot: "canary-retired-project" };
  expect(await cmdBindingRetirementApply(plan, "sha256:exact", true)).toBe(reply);
  expect(invoke).toHaveBeenLastCalledWith("checkout_apply", {
    plan, digest: "sha256:exact", confirmed: true, context: null, gitExecutable: null, retireBinding: true,
  });
  expect(JSON.stringify(useDebug.getState().log)).not.toContain("canary");
  expect(useDebug.getState().log[0].result).toBe(undefined);
});

it("routes an exact location plan without a replacement context and omits private shared traces", async () => {
  useDebug.setState({ debugMode: true });
  const reply = { ok: true, data: { root: "canary-private-location" }, error: null,
    error_code: null, warnings: [], continuations: [] };
  vi.mocked(invoke).mockResolvedValue(reply);
  const plan = { reader: "canary-private-reader" };
  expect(await cmdCheckoutLocationApply(plan, "sha256:exact", true, "/canary/git")).toBe(reply);
  expect(invoke).toHaveBeenLastCalledWith("checkout_location_apply", {
    plan, digest: "sha256:exact", confirmed: true, gitExecutable: "/canary/git",
  });
  vi.mocked(invoke).mockRejectedValue(new Error("canary-location-transport"));
  expect((await cmdCheckoutLocationApply(plan, "sha256:exact", true)).error_code).toBe("IPC_THROW");
  const entries = useDebug.getState().log;
  expect(entries).toHaveLength(2);
  expect(JSON.stringify(entries)).not.toContain("canary");
  expect(entries.every((entry) => entry.result === undefined)).toBe(true);
});


it("keeps the missing-checkout route fixed and omits private plans and results from traces", async () => {
  useDebug.setState({ debugMode: true });
  const reply = { ok: true, data: { private: "canary-missing-receipt" }, error: null,
    error_code: null, warnings: [], continuations: [] };
  vi.mocked(invoke).mockResolvedValue(reply);
  const plan = { kind: "corporate.project_binding.retire_missing", parent: "canary-private-parent" };
  expect(await cmdMissingBindingRetirementApply(plan, "sha256:exact", true)).toBe(reply);
  expect(invoke).toHaveBeenLastCalledWith("checkout_missing_binding_apply", {
    plan, digest: "sha256:exact", confirmed: true,
  });
  vi.mocked(invoke).mockRejectedValue(new Error("canary-missing-transport"));
  expect((await cmdMissingBindingRetirementApply(plan, "sha256:exact", true)).error_code).toBe("IPC_THROW");
  const entries = useDebug.getState().log;
  expect(entries).toHaveLength(2);
  expect(JSON.stringify(entries)).not.toContain("canary");
  expect(entries.every((entry) => entry.result === undefined)).toBe(true);
});
