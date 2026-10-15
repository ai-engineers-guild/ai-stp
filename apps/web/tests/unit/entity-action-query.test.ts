import { beforeEach, expect, it, vi } from "vitest";
import { loadEntityActionMenus } from "@/actions/entity-actions";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import { entityMenuResult, publicActions } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
vi.mock("@/actions/entity-actions", () => ({ loadEntityActionMenus: vi.fn() }));
const subject: EntityActionSubject = {
  kind: "team",
  id: "team_example",
  organization_id: "organization_example",
};
beforeEach(() => {
  vi.resetAllMocks();
});
it("batches concurrent requests at the contract bound without caching later reads", async () => {
  vi.mocked(loadEntityActionMenus).mockImplementation((subjects) =>
    Promise.resolve({
      csrfToken: "csrf",
      menus: {
        schema_version: 1,
        items: subjects.map((item) => entityMenuResult(item, publicActions).menu),
      },
    }),
  );
  const results = await Promise.all(
    Array.from({ length: 257 }, (_, index) =>
      queryEntityActionMenu({ ...subject, id: `team_${index}` }),
    ),
  );
  expect(loadEntityActionMenus).toHaveBeenCalledTimes(2);
  expect(vi.mocked(loadEntityActionMenus).mock.calls.map(([items]) => items.length)).toEqual([
    256, 1,
  ]);
  expect(results[256]?.menu.subject.id).toBe("team_256");
  await queryEntityActionMenu(subject);
  expect(loadEntityActionMenus).toHaveBeenCalledTimes(3);
});
it("rejects a mismatched response for the entire batch before resolving any entry", async () => {
  vi.mocked(loadEntityActionMenus).mockResolvedValue({
    csrfToken: "csrf",
    menus: {
      schema_version: 1,
      items: [
        entityMenuResult(subject, publicActions).menu,
        entityMenuResult({ ...subject, id: "wrong_entity" }, publicActions).menu,
      ],
    },
  });
  const results = await Promise.allSettled([
    queryEntityActionMenu(subject),
    queryEntityActionMenu({ ...subject, id: "team_other" }),
  ]);
  expect(results.map((result) => result.status)).toEqual(["rejected", "rejected"]);
});
