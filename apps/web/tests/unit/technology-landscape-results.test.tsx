import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import messages from "../../messages/en.json";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { landscape, categories, areas } from "@/mocks/technology-workspace-fixture";
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: ComponentProps<"a">) => <a {...props}>{children}</a>,
}));
afterEach(cleanup);
it("repeats a technology across categories while keeping one non-additive project count", () => {
  const row = landscape.items[0];
  const second = {
    ...categories[0],
    category_id: "category_01JQZK7B8N4M6P2R9T5V0X3Y80",
    name: "Web frameworks",
  };
  const data = {
    ...landscape,
    items: [
      {
        ...row,
        proposed_project_count: 1,
        technology: {
          ...row.technology,
          category_ids: [...row.technology.category_ids, second.category_id],
        },
      },
    ],
  };
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <TechnologyLandscapeResults
        landscape={data}
        filters={{ view: "grouped" }}
        categories={[...categories, second]}
        areas={areas}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("heading", { name: "API frameworks" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Web frameworks" })).toBeVisible();
  expect(screen.getAllByRole("table")).toHaveLength(1);
  expect(within(screen.getByRole("table")).getByRole("button", { name: "1" })).toBeVisible();
  fireEvent.click(
    screen.getAllByRole("button", { name: "FastAPI" }).at(0) ??
      screen.getByRole("button", { name: "FastAPI" }),
  );
  expect(
    within(screen.getByRole("dialog")).getByRole("link", { name: "Platform API" }),
  ).toHaveAttribute("href", expect.stringContaining(row.projects[0].project_id));
});
