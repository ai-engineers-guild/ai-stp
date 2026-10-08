import { NextIntlClientProvider } from "next-intl";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutationAction } from "@/actions/corporate";
import messages from "../../messages/en.json";
import russianMessages from "../../messages/ru.json";
import { TechnologyScanFindings } from "@/components/organisms/technology-scan-findings";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { TechnologyScanJournal } from "@/components/organisms/technology-scan-journal";
import { TechnologyFields } from "@/components/organisms/technology-registry-fields";
import { findingStatus } from "@/lib/technology-review-state";
import { displayCategoryIds } from "@/lib/technology-taxonomy";
import {
  authority,
  scan,
  projects,
  technologies,
  categories,
  areas,
  landscape,
} from "@/mocks/technology-workspace-fixture";
const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
  Link: ({ children, ...props }: { children: ReactNode; href: string }) => (
    <a {...props}>{children}</a>
  ),
}));
function wrap(children: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {children}
    </NextIntlClientProvider>
  );
}
const props = {
  ...authority,
  scans: [scan],
  projects,
  technologies,
  categories,
  areas,
  canUpdate: true,
};
afterEach(cleanup);
beforeEach(() => {
  mutation.mockReset();
  mutation.mockResolvedValue({ ok: true, data: { updated: 1 } });
  refresh.mockReset();
});
it("renders the area map and opens real versions and project evidence", () => {
  render(
    wrap(
      <TechnologyLandscapeResults
        landscape={landscape}
        filters={{ view: "grouped" }}
        categories={categories}
        areas={areas}
      />,
    ),
  );
  expect(screen.getByRole("heading", { name: "Technology landscape" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Server applications" })).toBeVisible();
  fireEvent.click(
    screen.getAllByRole("button", { name: "FastAPI" }).at(0) ??
      screen.getByRole("button", { name: "FastAPI" }),
  );
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByRole("link", { name: "Platform API" })).toBeVisible();
  expect(within(dialog).getAllByText(/0.115/).length).toBeGreaterThan(0);
});
it("provides the six reference summary columns and pagination", () => {
  render(
    wrap(
      <TechnologyLandscapeResults
        landscape={landscape}
        filters={{ view: "table" }}
        categories={categories}
        areas={areas}
      />,
    ),
  );
  for (const label of ["Technology", "Area", "Category", "Versions", "Projects", "Status"])
    expect(screen.getByRole("button", { name: label })).toBeVisible();
  expect(screen.getByRole("navigation", { name: "Pagination" })).toBeVisible();
});
it("translates unchanged taxonomy defaults, preserves owner names and keeps empty areas honest", () => {
  const first = landscape.items[0];
  const area = {
    ...areas[0],
    area_id: "area_00000000000000000000000001",
    name: "Languages and runtimes",
  };
  const category = {
    ...categories[0],
    category_id: "category_00000000000000000000001101",
    area_id: area.area_id,
    name: "Programming and query languages",
  };
  const technology = {
    ...technologies[0],
    category_ids: ["category_00000000000000000000000001", category.category_id],
  };
  render(
    <NextIntlClientProvider locale="ru" messages={russianMessages}>
      <TechnologyLandscapeResults
        landscape={{ ...landscape, items: [{ ...first, technology }] }}
        filters={{ view: "grouped" }}
        categories={[category]}
        areas={[
          area,
          { ...area, area_id: "area_00000000000000000000000002", name: "Owner interfaces" },
        ]}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("heading", { name: "Языки и среды выполнения" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Owner interfaces" })).toBeVisible();
  expect(screen.getByText("Нет найденных технологий")).toBeVisible();
  expect(displayCategoryIds(technology)).toEqual([category.category_id]);
});
it("searches the category directory and submits selected IDs through the ordinary registry form", () => {
  render(
    wrap(
      <form aria-label="Registry">
        <TechnologyFields prefix="taxonomy" categories={categories} initial={undefined} />
      </form>,
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Categories" }));
  fireEvent.change(screen.getByRole("searchbox", { name: messages.technology.search }), {
    target: { value: "API frameworks" },
  });
  fireEvent.click(screen.getByRole("checkbox", { name: "API frameworks" }));
  const form = screen.getByRole<HTMLFormElement>("form", { name: "Registry" });
  expect(new FormData(form).getAll("category_ids")).toEqual([categories[0].category_id]);
});
it("keeps the finding editor beside the table and edits resolved findings", async () => {
  render(wrap(<TechnologyScanFindings {...props} />));
  expect(screen.getByRole("complementary", { name: "Finding review" })).toBeVisible();
  fireEvent.change(screen.getByRole("textbox", { name: "Comment" }), {
    target: { value: "Reviewed from manifest" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm and apply" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledTimes(1);
  });
  const input = mutation.mock.calls[0]?.[0];
  expect(input?.method).toBe("PUT");
  expect(input?.path).toContain("technology-findings/review");
  expect(input?.body).toMatchObject({
    items: [
      {
        scan_id: scan.scan_id,
        coordinate: "fastapi",
        technology_id: technologies[0].technology_id,
        expected_revision: 1,
        comment: "Reviewed from manifest",
        review: "confirmed",
      },
    ],
  });
});
it("excludes an unrecognized finding with its original coordinate and resets local edits", async () => {
  render(wrap(<TechnologyScanFindings {...props} mode="mapping" />));
  fireEvent.click(screen.getByRole("button", { name: "weirdlib" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Comment" }), {
    target: { value: "Temporary edit" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Reset" }));
  expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "Exclude finding" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    items: [
      {
        coordinate: "weirdlib",
        technology_id: null,
        review: "rejected",
        expected_revision: 0,
      },
    ],
  });
});
it("filters scan history by source and search and shows the repository in its project cell", () => {
  render(wrap(<TechnologyScanJournal items={[scan]} projects={projects} />));
  expect(screen.getByText(scan.repository)).toBeVisible();
  expect(screen.getByText(/10:00/)).toBeVisible();
  fireEvent.change(screen.getByRole("combobox", { name: "Source" }), {
    target: { value: "github" },
  });
  expect(screen.queryByRole("link", { name: scan.scan_id })).toBeNull();
  fireEvent.change(screen.getByRole("combobox", { name: "Source" }), {
    target: { value: "gitlab" },
  });
  expect(screen.getByRole("link", { name: scan.scan_id })).toBeVisible();
});
it("shows empty and read-only states without write actions", () => {
  render(wrap(<TechnologyScanFindings {...props} canUpdate={false} scans={[]} />));
  expect(screen.getByText("Select a finding to review.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Confirm and apply" })).toBeNull();
});

it("retains confirmed history and archived names without offering archived records for selection", () => {
  const archived = { ...technologies[0], lifecycle: "archived" as const };
  const category = { ...categories[0], state: "archived" as const };
  const finding = { ...scan.findings[0], review: "confirmed" as const };
  render(
    wrap(
      <TechnologyScanFindings
        {...props}
        technologies={[archived]}
        categories={[category]}
        scans={[{ ...scan, findings: [finding] }]}
      />,
    ),
  );
  const row = screen.getByRole("button", { name: "fastapi" }).closest("tr");
  expect(row).toHaveTextContent("FastAPI");
  expect(row).toHaveTextContent("API frameworks");
  expect(row).toHaveTextContent("Confirmed");
  expect(screen.getByRole("button", { name: "Confirm and apply" })).toBeDisabled();
  expect(screen.getByRole("option", { name: "API frameworks" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Technology: FastAPI" }));
  expect(screen.queryByRole("checkbox", { name: "FastAPI" })).toBeNull();
  expect(findingStatus({ ...finding, scan }, new Map())).toBe("resolved");
  expect(findingStatus({ ...finding, review: "rejected", scan }, new Map())).toBe("rejected");
});
