import { beforeEach, expect, it, vi } from "vitest";
import { useContexts } from "./contexts";
import * as transport from "./transport";
import type { CmdResult } from "./transport";

vi.mock("./transport", () => ({
  cliPlan: vi.fn(),
  cmdProfileApply: vi.fn(),
  cmdRunRead: vi.fn(),
}));
const A = "context_01ARZ3NDEKTSV4RRFFQ69G5FAV",
  B = "context_01ARZ3NDEKTSV4RRFFQ69G5FAW";
const ok = (data: Record<string, unknown>): CmdResult => ({
  ok: true,
  data,
  error: null,
  error_code: null,
  warnings: [],
  continuations: [],
});
function list(selected: string): CmdResult {
  return ok({
    selected: { context_id: selected },
    contexts: [A, B].map((id) => ({
      context: {
        context_id: id,
        label: id,
        authority: {
          kind: "remote",
          organization: { kind: "corporate", display_name: id },
          account: {
            origin: "https://company.example.test",
            connection: { connection_id: `connection_${id}` },
          },
        },
      },
    })),
  });
}
beforeEach(() => {
  vi.resetAllMocks();
  useContexts.setState({
    views: [],
    selected: null,
    result: null,
    loading: false,
    switching: false,
  });
});

it("retains the latest forced context read when an older reply arrives last", async () => {
  let finish!: (result: CmdResult) => void;
  vi.mocked(transport.cmdRunRead)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce(list(B));
  const first = useContexts.getState().refresh(true);
  await useContexts.getState().refresh(true);
  finish(list(A));
  await first;
  expect(useContexts.getState().selected?.id).toBe(B);
});

it("applies only the exact selected preference plan and then reads actual selection", async () => {
  vi.mocked(transport.cmdRunRead)
    .mockResolvedValueOnce(list(A))
    .mockResolvedValueOnce(list(B));
  await useContexts.getState().refresh(true);
  const plan = {
    schema_version: 1,
    change: { action: "select", context: { context_id: B } },
  };
  const digest = `sha256:${"a".repeat(64)}`;
  vi.mocked(transport.cliPlan).mockResolvedValue(
    ok({ plan, plan_digest: digest }),
  );
  vi.mocked(transport.cmdProfileApply).mockResolvedValue(ok({ context_id: B }));
  expect((await useContexts.getState().select(B)).ok).toBe(true);
  expect(transport.cmdProfileApply).toHaveBeenCalledWith(
    "context apply",
    plan,
    digest,
    true,
  );
  expect(useContexts.getState().selected?.id).toBe(B);
  expect(useContexts.getState().switching).toBe(false);
});

it("refuses a different plan target and preserves the actual current view", async () => {
  vi.mocked(transport.cmdRunRead).mockResolvedValue(list(A));
  await useContexts.getState().refresh(true);
  vi.mocked(transport.cliPlan).mockResolvedValue(
    ok({
      plan: { change: { action: "select", context: { context_id: A } } },
      plan_digest: `sha256:${"a".repeat(64)}`,
    }),
  );
  expect((await useContexts.getState().select(B)).ok).toBe(false);
  expect(transport.cmdProfileApply).not.toHaveBeenCalled();
  expect(useContexts.getState().selected?.id).toBe(A);
});

it("clears stale company metadata when the current selected view is invalid", async () => {
  vi.mocked(transport.cmdRunRead)
    .mockResolvedValueOnce(list(A))
    .mockResolvedValueOnce(ok({ contexts: [], selected: { context_id: A } }));
  await useContexts.getState().refresh(true);
  await useContexts.getState().refresh(true);
  expect(useContexts.getState().selected).toBe(null);
  expect(useContexts.getState().views).toEqual([]);
  expect(useContexts.getState().result?.ok).toBe(false);
});
