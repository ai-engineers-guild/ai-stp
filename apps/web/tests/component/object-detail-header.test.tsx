import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/features/gate", () => ({
  isFeatureEnabled: (key: string) => key === "catalog_usage_metrics",
}));

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { ObjectDetailFrame } from "@/components/organisms/object-detail-frame";
import { ObjectDetailHeader } from "@/components/organisms/object-detail-header";

const like = {
  stableId: "component_example",
  sharePath: "/en/catalog/components/component_example/versions/1.0",
  likesCount: 2,
  reportHref: undefined,
  labels: {
    copyUrl: "Copy URL",
    share: "Share",
    copyId: "Copy ID",
    copied: "Copied",
    like: "Like",
    unlike: "Liked",
    more: "More actions",
    report: "Report",
  },
};

describe("object detail header and frame", () => {
  it("pins a vertical overflow trigger and keeps stars beside the source link", () => {
    const { container } = render(
      <ObjectDetailHeader
        icon={<span>icon</span>}
        title="ai-repo-safety"
        badges={<span>experimental</span>}
        versionLabel="v0.1"
        githubStars={2}
        githubStarsLabel="GitHub stars"
        archived={true}
        archivedLabel="Archived"
        source={{
          repository: "https://github.com/example/ai-repo-safety",
          commit: "a".repeat(40),
          path: "",
        }}
        viewSourceLabel="View source on GitHub"
        like={like}
      />,
    );
    const header = container.querySelector('[data-ui="component-detail-header"]');
    const overflow = container.querySelector('[data-ui="component-overflow"]');
    expect(header).not.toBeNull();
    expect(overflow?.className).toContain("absolute");
    expect(overflow?.className).toContain("top-0");
    expect(overflow?.className).toContain("right-0");
    expect(header?.contains(overflow)).toBe(true);

    const more = screen.getByRole("button", { name: "More actions" });
    expect(more.querySelector("svg.lucide-ellipsis-vertical")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Like · 2" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Share" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("GitHub stars: 2")).toBeVisible();
    expect(screen.getByRole("link", { name: "View source on GitHub" })).toHaveAttribute(
      "href",
      `https://github.com/example/ai-repo-safety/commit/${"a".repeat(40)}`,
    );
    expect(screen.getByText("Archived")).toBeVisible();
    const actions = container.querySelector('[data-ui="component-actions"]');
    expect(actions?.contains(screen.getByLabelText("GitHub stars: 2"))).toBe(true);
    expect(actions?.contains(screen.getByRole("link", { name: "View source on GitHub" }))).toBe(
      true,
    );
  });

  it("omits stars and source when GitHub data is absent", () => {
    render(
      <ObjectDetailHeader
        icon={<span>icon</span>}
        title="local-only"
        badges={null}
        versionLabel="v1.0"
        githubStars={null}
        githubStarsLabel="GitHub stars"
        archived={false}
        archivedLabel="Archived"
        source={null}
        viewSourceLabel="View source on GitHub"
        like={like}
      />,
    );
    expect(screen.queryByLabelText(/Detail views/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/GitHub stars/)).not.toBeInTheDocument();
    expect(screen.queryByText("Archived")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View source on GitHub" })).not.toBeInTheDocument();
  });

  it("keeps usage aggregates out of the detail header", () => {
    render(
      <ObjectDetailHeader
        icon={<span>icon</span>}
        title="counted"
        badges={null}
        versionLabel="v1.0"
        githubStars={null}
        githubStarsLabel="GitHub stars"
        archived={null}
        archivedLabel="Archived"
        source={null}
        viewSourceLabel="View source on GitHub"
        like={like}
      />,
    );
    expect(screen.queryByLabelText(/Detail views/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Artifact downloads/)).not.toBeInTheDocument();
    expect(screen.queryByText(/install/i)).not.toBeInTheDocument();
  });

  it("hides owner-only overflow items from visitors", async () => {
    const user = userEvent.setup();
    render(
      <ObjectDetailHeader
        icon={<span>icon</span>}
        title="visitor"
        badges={null}
        versionLabel="v1.0"
        githubStars={null}
        githubStarsLabel="GitHub stars"
        archived={null}
        archivedLabel="Archived"
        source={null}
        viewSourceLabel="View source on GitHub"
        like={like}
      />,
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByRole("menuitem", { name: /Edit bio/ })).not.toBeInTheDocument();
  });

  it("uses a two-column description/media grid and a lower passport column", () => {
    const { container } = render(
      <ObjectDetailFrame
        description={<p>Description</p>}
        media={<p>Media</p>}
        main={<p>Main</p>}
        rail={<p>Author</p>}
        passport={<p>Passport</p>}
      />,
    );
    expect(container.querySelector('[data-ui="component-description-media"]')?.className).toContain(
      "lg:grid-cols-[minmax(0,1fr)_16rem]",
    );
    expect(container.querySelector('[data-ui="component-detail-lower"]')?.className).toContain(
      "lg:grid-cols-[minmax(0,1fr)_22rem]",
    );
    expect(container.querySelector('[data-ui="component-detail-main"]')).toHaveTextContent("Main");
    expect(container.querySelector('[data-ui="component-detail-rail"]')).toHaveTextContent(
      "Author",
    );
  });

  it("does not reserve a media column when media is absent", () => {
    const { container } = render(
      <ObjectDetailFrame description={<p>Description</p>} main={<p>Main</p>} rail={<p>Rail</p>} />,
    );
    expect(
      container.querySelector('[data-ui="component-description-media"]')?.className,
    ).not.toContain("16rem");
  });

  it("keeps 44px actions and puts the install rail first on a narrow viewport", () => {
    const { container } = render(
      <ObjectDetailHeader
        icon={<span>icon</span>}
        title="narrow-detail"
        badges={null}
        versionLabel="v1.0"
        githubStars={4}
        githubStarsLabel="GitHub stars"
        archived={false}
        archivedLabel="Archived"
        source={{
          repository: "https://github.com/example/narrow-detail",
          commit: "b".repeat(40),
          path: "",
        }}
        viewSourceLabel="View source on GitHub"
        like={like}
      />,
    );
    expect(screen.getByRole("button", { name: "Like · 2" })).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "More actions" })).toHaveClass("size-11");
    expect(screen.getByRole("link", { name: "View source on GitHub" })).toHaveClass("min-h-11");
    expect(container.querySelector('[data-ui="component-detail-header"]')).toHaveClass(
      "overflow-x-clip",
    );

    const { container: frame } = render(
      <ObjectDetailFrame
        description={<p>Description</p>}
        main={<p>Main</p>}
        rail={<h2>Use via CLI</h2>}
      />,
    );
    expect(frame.querySelector('[data-ui="component-detail-rail"]')?.className).toContain(
      "order-1",
    );
    expect(frame.querySelector('[data-ui="component-detail-rail"]')?.className).toContain(
      "lg:order-2",
    );
  });
});
