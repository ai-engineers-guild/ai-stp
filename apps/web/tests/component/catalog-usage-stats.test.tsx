import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const gate = vi.hoisted(() => ({ enabled: true }));

vi.mock("@/lib/features/gate", () => ({
  isFeatureEnabled: (key: string) => gate.enabled && key === "catalog_usage_metrics",
}));

const { CatalogUsageStats } = await import("@/components/molecules/catalog-usage-stats");

describe("CatalogUsageStats", () => {
  it("hides counters when the show flag is off even if API sent values", () => {
    gate.enabled = false;
    const { container } = render(
      <CatalogUsageStats
        metrics={{ schema_version: 1, detail_views_count: 9, artifact_downloads_count: 3 }}
        locale="en"
        viewsLabel="Detail views"
        downloadsLabel="Artifact downloads"
      />,
    );
    expect(container).toBeEmptyDOMElement();
    gate.enabled = true;
  });

  it("does not invent zeroes when the aggregate is absent", () => {
    const { container } = render(
      <CatalogUsageStats
        metrics={null}
        locale="en"
        viewsLabel="Detail views"
        downloadsLabel="Artifact downloads"
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows compact labeled counts without install wording", () => {
    render(
      <CatalogUsageStats
        metrics={{ schema_version: 1, detail_views_count: 4, artifact_downloads_count: 2 }}
        locale="en"
        viewsLabel="Detail views"
        downloadsLabel="Artifact downloads"
      />,
    );
    expect(screen.getByLabelText("Detail views: 4")).toBeInTheDocument();
    expect(screen.getByLabelText("Artifact downloads: 2")).toBeInTheDocument();
    expect(screen.queryByText(/install/i)).not.toBeInTheDocument();
  });

  it("keeps long Russian labels from forcing a fixed width", () => {
    render(
      <CatalogUsageStats
        metrics={{ schema_version: 1, detail_views_count: 1, artifact_downloads_count: 0 }}
        locale="ru"
        viewsLabel="Просмотры публичной страницы объекта"
        downloadsLabel="Успешные скачивания байтов артефакта"
      />,
    );
    const group = screen.getByLabelText(/Просмотры публичной страницы объекта: 1/u);
    expect(group.className).toMatch(/min-w-0/u);
    expect(group.className).not.toMatch(/w-\[/u);
  });
});
