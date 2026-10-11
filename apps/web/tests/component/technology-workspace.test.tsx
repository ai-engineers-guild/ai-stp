import userEvent from "@testing-library/user-event";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { NextIntlClientProvider } from "next-intl";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutation } from "@/lib/api/corporate-mutation";
import messages from "../../messages/en.json";
import russianMessages from "../../messages/ru.json";
import { TechnologyScanFindings } from "@/components/organisms/technology-scan-findings";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { TechnologyScanJournal } from "@/components/organisms/technology-scan-journal";
import { TechnologyFields } from "@/components/organisms/technology-registry-fields";
import { findingStatus, groupFindingRows } from "@/lib/technology-review-state";
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
const { mutation, refresh, push, download } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutation>(),
  refresh: vi.fn(),
  push: vi.fn(),
  download: vi.fn(),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: mutation }));
vi.mock("@/lib/findings-export", () => ({ downloadScanFindings: download }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh, push, replace: vi.fn() }),
  usePathname: () => "/corporate/technology-mappings",
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
  push.mockReset();
  download.mockReset();
});
it("renders the area map and opens real versions and project evidence", () => {
  render(
    wrap(
      <TechnologyLandscapeResults
        landscape={landscape}
        filters={{}}
        categories={categories}
        areas={areas}
      />,
    ),
  );
  expect(screen.getByRole("heading", { name: "Technology landscape" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Server applications" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /API frameworks/ }));
  fireEvent.click(
    screen.getAllByRole("button", { name: "FastAPI" }).at(0) ??
      screen.getByRole("button", { name: "FastAPI" }),
  );
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByRole("link", { name: "Platform API" })).toBeVisible();
  expect(within(dialog).getAllByText(/0.115/).length).toBeGreaterThan(0);
});
it("keeps cards compact and expands categories through the area menu", async () => {
  render(
    wrap(
      <TechnologyLandscapeResults
        landscape={landscape}
        filters={{}}
        categories={categories}
        areas={areas}
      />,
    ),
  );
  expect(screen.queryByRole("button", { name: "FastAPI" })).toBeNull();
  const user = userEvent.setup();
  const areaActions = () =>
    screen.getAllByRole("button", { name: "Area actions" }).at(0) ??
    screen.getByRole("button", { name: "Area actions" });
  await user.click(areaActions());
  await user.click(await screen.findByRole("menuitem", { name: "Expand all" }));
  expect(screen.getByRole("button", { name: "FastAPI" })).toBeVisible();
  await user.click(areaActions());
  await user.click(await screen.findByRole("menuitem", { name: "Collapse all" }));
  expect(screen.queryByRole("button", { name: "FastAPI" })).toBeNull();
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
        filters={{}}
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
it("edits categories inline and filters out classified findings", async () => {
  render(wrap(<TechnologyScanFindings {...props} />));
  expect(screen.queryByRole("complementary")).toBeNull();
  expect(screen.queryByRole("textbox", { name: "Comment" })).toBeNull();
  // Technologies and declared-but-unrecognized dependencies list separately.
  expect(screen.getByRole("heading", { name: "Technologies" })).toBeVisible();
  const dependencies = screen.getByRole("region", { name: "Dependencies" });
  expect(within(dependencies).getByText("left-pad")).toBeVisible();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Filters/ }));
  await user.click(screen.getByRole("checkbox", { name: "Only findings needing review" }));
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(screen.queryByText("fastapi")).toBeNull();
  const row = screen.getByText("weirdlib").closest("tr");
  if (!row) throw new Error("Missing finding row");
  fireEvent.click(
    within(row).getByRole("button", { name: "Category: weirdlib: Choose a category" }),
  );
  fireEvent.click(within(row).getByRole("checkbox", { name: "API frameworks" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledTimes(1);
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    items: [
      {
        coordinate: "weirdlib",
        category_id: categories[0].category_id,
        technology_id: null,
        review: "confirmed",
      },
    ],
  });
});
it("groups versions and contexts while retaining every review identity and source", () => {
  const first = scan.findings[0];
  const rows = groupFindingRows([
    {
      ...scan,
      findings: [
        first,
        { ...first, version: "0.116", context: "development", evidence: scan.findings[1].evidence },
        { ...first, version: "0.117" },
      ],
    },
  ]);
  expect(rows).toHaveLength(1);
  expect(rows[0]?.members).toHaveLength(2);
  expect(rows[0]?.evidence).toHaveLength(2);
  expect(rows[0]?.version).toBe("0.115, 0.116, 0.117");
});
it("filters scan history by source and search and shows the repository in its project cell", async () => {
  render(wrap(<TechnologyScanJournal items={[scan]} projects={projects} />));
  expect(screen.getByText(scan.repository)).toBeVisible();
  expect(screen.getByText(/10:00/)).toBeVisible();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Filters/ }));
  await user.click(screen.getByRole("button", { name: /Source/ }));
  await user.click(screen.getByRole("checkbox", { name: "GitHub" }));
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(screen.queryByRole("link", { name: scan.scan_id })).toBeNull();
  await user.click(screen.getByRole("button", { name: /Filters/ }));
  await user.click(screen.getByRole("button", { name: /Source/ }));
  await user.click(screen.getByRole("checkbox", { name: "GitLab" }));
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(screen.getByRole("link", { name: scan.scan_id })).toBeVisible();
});
it("shows empty and read-only states without write actions", () => {
  render(wrap(<TechnologyScanFindings {...props} canUpdate={false} scans={[]} />));
  expect(screen.getByRole("status")).toBeVisible();
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
  const row = screen.getByText("FastAPI").closest("tr");
  expect(row).toBeVisible();
  expect(row).toHaveTextContent("API frameworks");
  expect(screen.queryByRole("button", { name: "Confirm and apply" })).toBeNull();
  expect(findingStatus({ ...finding, scan }, new Map())).toBe("resolved");
  expect(findingStatus({ ...finding, review: "rejected", scan }, new Map())).toBe("rejected");
});

it("offers findings downloads by scope and format", async () => {
  render(wrap(<TechnologyScanFindings {...props} />));
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Download findings" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("Scope")).toBeVisible();
  expect(within(dialog).getByLabelText("Format")).toBeVisible();
  fireEvent.change(within(dialog).getByLabelText("Format"), { target: { value: "csv" } });
  fireEvent.change(within(dialog).getByLabelText("Scope"), {
    target: { value: "technologies" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Download findings" }));
  expect(download).toHaveBeenCalledWith(
    expect.objectContaining({ scan_id: scan.scan_id }),
    "csv",
    "technologies",
  );
});
it("opens journal actions without navigating, and navigates from the row body", async () => {
  render(wrap(<TechnologyScanJournal items={[scan]} projects={projects} />));
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Actions" }));
  expect(screen.getByRole("menu")).toBeVisible();
  expect(push).not.toHaveBeenCalled();
  await user.keyboard("{Escape}");
  fireEvent.click(screen.getByText("312 sec"));
  expect(push).toHaveBeenCalledWith(`/corporate/technology-scans/${scan.scan_id}`);
});
it("creates a technology with only a name", async () => {
  render(
    wrap(
      <TechnologyRegistryCreate
        kind="technology"
        {...authority}
        authorizationRevision={String(authority.authorizationRevision)}
        categories={categories}
        areas={areas}
      />,
    ),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
    target: { value: "New library" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create technology draft" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledTimes(1);
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    metadata: { name: "New library", category_ids: [], description: "" },
  });
});
