import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useRequestedEntityAction } from "@/lib/use-requested-entity-action";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import { entityMenuResult } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";

const { translate } = vi.hoisted(() => ({ translate: (key: string) => key }));
vi.mock("next-intl", () => ({ useTranslations: () => translate }));
vi.mock("@/lib/entity-action-query", () => ({ queryEntityActionMenu: vi.fn() }));
const subject: EntityActionSubject = { kind: "job_title", id: "title_1", organization_id: "org_1" };
beforeEach(() => vi.resetAllMocks());

it("opens a linked operation only after the server returns that action", async () => {
  const open = vi.fn();
  vi.mocked(queryEntityActionMenu).mockResolvedValue(entityMenuResult(subject, []));
  const hook = renderHook(
    ({ action }) => {
      useRequestedEntityAction(subject, action, open);
    },
    {
      initialProps: { action: "restore" },
    },
  );
  await waitFor(() => {
    expect(queryEntityActionMenu).toHaveBeenCalledOnce();
  });
  expect(open).not.toHaveBeenCalled();
  vi.mocked(queryEntityActionMenu).mockResolvedValue(entityMenuResult(subject, ["edit"]));
  hook.rerender({ action: "edit" });
  await waitFor(() => {
    expect(open).toHaveBeenCalledOnce();
  });
});

it("does not execute an old entity response after the subject changes", async () => {
  const open = vi.fn();
  let resolveOld: ((value: ReturnType<typeof entityMenuResult>) => void) | undefined;
  vi.mocked(queryEntityActionMenu)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValueOnce(entityMenuResult({ ...subject, id: "title_2" }, []));
  const hook = renderHook(
    ({ entity }) => {
      useRequestedEntityAction(entity, "edit", open);
    },
    {
      initialProps: { entity: subject },
    },
  );
  hook.rerender({ entity: { ...subject, id: "title_2" } });
  resolveOld?.(entityMenuResult(subject, ["edit"]));
  await waitFor(() => {
    expect(queryEntityActionMenu).toHaveBeenCalledTimes(2);
  });
  expect(open).not.toHaveBeenCalled();
});
