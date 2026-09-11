import { beforeEach, describe, expect, it, vi } from "vitest";

import { LOCAL_CONTEXT } from "@/lib/product-context";

const values = new Map<string, string>();
const contextRequest = vi.fn();

vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) => {
        const value = values.get(name);
        return value ? { value } : undefined;
      },
    }),
}));
vi.mock("@/lib/api/http", () => ({ privateApiRequest: contextRequest }));
vi.mock("@/lib/env", () => ({ getEnv: () => ({ AI_STP_USE_MOCKS: true }) }));

describe("product context server", () => {
  beforeEach(() => {
    values.clear();
    contextRequest.mockReset();
  });

  it("does not call a remote organization endpoint for local mode", async () => {
    values.set("ai_stp_product_mode", "local");
    contextRequest.mockResolvedValue(LOCAL_CONTEXT);

    const { loadProductContext } = await import("@/lib/product-context-server");
    const snapshot = await loadProductContext();

    expect(snapshot.status).toBe("ready");
    expect(contextRequest).toHaveBeenCalledOnce();
    expect(contextRequest).toHaveBeenCalledWith("/v1/context", {
      headers: { "X-AI-STP-Product-Mode": "local" },
    });
  });
});
