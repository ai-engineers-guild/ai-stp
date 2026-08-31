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
    expect(screen.getByText("Detail views:")).toBeInTheDocument();
    expect(screen.getByText("Artifact downloads:")).toBeInTheDocument();
    expect(screen.queryByText(/install/i)).not.toBeInTheDocument();
  });

  it("keeps long Russian labels from forcing a fixed width", () => {
    render(
      <CatalogUsageStats
        metrics={{ schema_version: 1, detail_views_count: 1, artifact_downloads_count: 0 }}
        locale="ru"
        viewsLabel={
          "\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u044b \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u043e\u0439 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b \u043e\u0431\u044a\u0435\u043a\u0442\u0430"
        }
        downloadsLabel={
          "\u0423\u0441\u043f\u0435\u0448\u043d\u044b\u0435 \u0441\u043a\u0430\u0447\u0438\u0432\u0430\u043d\u0438\u044f \u0431\u0430\u0439\u0442\u043e\u0432 \u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\u0430"
        }
      />,
    );
    const group = screen.getByText(
      /\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u044b \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u043e\u0439 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b \u043e\u0431\u044a\u0435\u043a\u0442\u0430:/u,
    ).parentElement;
    expect(group).not.toBeNull();
    if (!group) throw new Error("expected usage group");
    expect(group.className).toMatch(/min-w-0/u);
    expect(group.className).not.toMatch(/w-\[/u);
  });
});
