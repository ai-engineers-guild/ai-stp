import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import messages from "../../messages/en.json";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { landscape, categories, areas } from "@/mocks/technology-workspace-fixture";
import type { CategoryView } from "@/lib/api/generated/types.gen";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: ComponentProps<"a">) => <a {...props}>{children}</a>,
}));

afterEach(cleanup);

function renderLandscape(
  data: typeof landscape = landscape,
  extraCategories: CategoryView[] = [],
  filters: Record<string, string | string[]> = {},
) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <TechnologyLandscapeResults
        landscape={data}
        filters={filters}
        categories={[...categories, ...extraCategories]}
        areas={areas}
      />
    </NextIntlClientProvider>,
  );
}

it("groups technologies under category rows inside one card per area", () => {
  const row = landscape.items[0];
  const second = {
    ...categories[0],
    category_id: "category_01JQZK7B8N4M6P2R9T5V0X3Y80",
    name: "Web frameworks",
  };
  const data: typeof landscape = {
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
  renderLandscape(data, [second]);
  expect(screen.getByRole("heading", { name: "Server applications" })).toBeVisible();
  expect(screen.getByRole("button", { name: /API frameworks/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Web frameworks/ })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /API frameworks/ }));
  fireEvent.click(
    screen.getAllByRole("button", { name: "FastAPI" }).at(0) ??
      screen.getByRole("button", { name: "FastAPI" }),
  );
  expect(
    within(screen.getByRole("dialog")).getByRole("link", { name: "Platform API" }),
  ).toHaveAttribute("href", expect.stringContaining(row.projects[0].project_id));
});

it("limits categories to five and reveals the rest through the +N counter", () => {
  const row = landscape.items[0];
  const extra = Array.from({ length: 6 }, (_, index) => ({
    ...categories[0],
    category_id: `category_01JQZK7B8N4M6P2R9T5V0X4Y${index}`,
    name: `Extra category ${index}`,
  }));
  const data: typeof landscape = {
    ...landscape,
    items: [
      {
        ...row,
        technology: {
          ...row.technology,
          category_ids: [
            ...row.technology.category_ids,
            ...extra.map((category) => category.category_id),
          ],
        },
      },
    ],
  };
  renderLandscape(data, extra);
  expect(screen.queryByRole("button", { name: /Extra category 5/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Show 2 more categories" }));
  expect(screen.getByRole("button", { name: /Extra category 5/ })).toBeVisible();
});

it("merges categories without an area into a single unclassified card", () => {
  const row = landscape.items[0];
  const loose = Array.from({ length: 2 }, (_, index) => ({
    ...categories[0],
    category_id: `category_01JQZK7B8N4M6P2R9T5V0X5Y${index}`,
    name: `Loose category ${index}`,
    area_id: null,
  }));
  const data: typeof landscape = {
    ...landscape,
    items: [
      {
        ...row,
        technology: {
          ...row.technology,
          category_ids: loose.map((category) => category.category_id),
        },
      },
    ],
  };
  renderLandscape(data, loose);
  expect(screen.getAllByRole("heading", { name: "Unclassified" })).toHaveLength(1);
  expect(screen.getByRole("button", { name: /Loose category 0/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Loose category 1/ })).toBeVisible();
});

it("expands and collapses every category through the area action menu", async () => {
  const user = userEvent.setup();
  renderLandscape();
  await user.click(screen.getByRole("button", { name: "Area actions" }));
  await user.click(await screen.findByRole("menuitem", { name: "Expand all" }));
  expect(screen.getByRole("button", { name: "FastAPI" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Area actions" }));
  expect(await screen.findByRole("menuitem", { name: "Open technology list" })).toHaveAttribute(
    "href",
    expect.stringContaining(`area_ids=${areas[0].area_id}`),
  );
  await user.click(screen.getByRole("menuitem", { name: "Collapse all" }));
  expect(screen.queryByRole("button", { name: "FastAPI" })).toBeNull();
});

it("renders the sortable table view instead of area cards when view=table", async () => {
  const user = userEvent.setup();
  renderLandscape(landscape, [], { view: "table" });
  expect(screen.queryByRole("heading", { name: "Server applications" })).toBeNull();
  const table = screen.getByRole("table", { name: "Technology summary" });
  const nameButtons = within(table).getAllByRole("button", { name: "FastAPI" });
  expect(nameButtons.length).toBeGreaterThan(0);
  const nameButton = nameButtons[0];
  if (!nameButton) throw new Error("FastAPI button is missing");
  await user.click(nameButton);
  expect(screen.getByRole("dialog")).toBeVisible();
});
