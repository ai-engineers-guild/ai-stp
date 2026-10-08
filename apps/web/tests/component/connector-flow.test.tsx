import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useConnectorFlow, type ConnectorResult } from "@/lib/use-connector-flow";

type Status = {
  connections: Array<{ purpose: string; state: string; configured: boolean }>;
};

const connectedStatus: Status = {
  connections: [{ purpose: "source", state: "connected", configured: true }],
};
const disconnectedStatus: Status = {
  connections: [{ purpose: "source", state: "disconnected", configured: true }],
};

vi.mock("@/lib/connection-flow", () => ({
  openConnectionWindow: vi.fn(() => null),
  navigateConnectionWindow: vi.fn(),
  watchConnection: vi.fn(() => () => {}),
}));

function ok<T>(data: T): ConnectorResult<T> {
  return { ok: true, data };
}
function fail(code = "denied"): ConnectorResult<never> {
  return { ok: false, code };
}

describe("useConnectorFlow", () => {
  it("loads status on mount and derives source/admin/connected", async () => {
    const { result } = renderHook(() =>
      useConnectorFlow<Status>({
        fetchStatus: () => Promise.resolve(ok(connectedStatus)),
        requestConnect: () => Promise.resolve(ok({ authorization_url: "https://x" })),
        deps: [],
      }),
    );
    await waitFor(() => expect(result.current.status).toEqual(connectedStatus));
    expect(result.current.connected).toBe(true);
    expect(result.current.source?.state).toBe("connected");
    expect(result.current.admin).toBeUndefined();
  });

  it("surfaces a failed status fetch as an error code", async () => {
    const { result } = renderHook(() =>
      useConnectorFlow<Status>({
        fetchStatus: () => Promise.resolve(fail("unauthorized")),
        requestConnect: () => Promise.resolve(ok({ authorization_url: "https://x" })),
        deps: [],
      }),
    );
    await waitFor(() => expect(result.current.error).toBe("unauthorized"));
    expect(result.current.status).toBeNull();
  });

  it("run() reports failure through error and the failed callback", async () => {
    const { result } = renderHook(() =>
      useConnectorFlow<Status>({
        fetchStatus: () => Promise.resolve(ok(disconnectedStatus)),
        requestConnect: () => Promise.resolve(ok({ authorization_url: "https://x" })),
        deps: [],
      }),
    );
    const failed = vi.fn();
    act(() => {
      result.current.run(() => Promise.resolve(fail("rate_limited")), vi.fn(), failed);
    });
    await waitFor(() => expect(result.current.error).toBe("rate_limited"));
    expect(failed).toHaveBeenCalledOnce();
  });

  it("connect() opens the popup and starts polling", async () => {
    const flow = await import("@/lib/connection-flow");
    const { result } = renderHook(() =>
      useConnectorFlow<Status>({
        fetchStatus: () => Promise.resolve(ok(connectedStatus)),
        requestConnect: () => Promise.resolve(ok({ authorization_url: "https://auth" })),
        deps: [],
      }),
    );
    await act(async () => {
      result.current.connect("source");
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(flow.navigateConnectionWindow).toHaveBeenCalledWith(null, "https://auth"),
    );
    expect(flow.watchConnection).toHaveBeenCalledOnce();
  });
});
