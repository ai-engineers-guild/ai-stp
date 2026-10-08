import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PagePager } from "@/components/molecules/page-pager";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const controls = {
  previous: "Previous page",
  next: "Next page",
  page: (value: number) => `Page ${value}`,
};

describe("PagePager", () => {
  it("renders link-mode pages with the current page marked", () => {
    render(
      <PagePager
        label="Pagination"
        page={4}
        totalPages={12}
        controls={controls}
        hrefFor={(page) => `/catalog?page=${page}`}
      />,
    );
    const nav = screen.getByRole("navigation", { name: "Pagination" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Page 5" })).toHaveAttribute("href", "/catalog?page=5");
    expect(screen.getByRole("link", { name: "Page 4" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute(
      "href",
      "/catalog?page=3",
    );
  });

  it("collapses a long range into gaps", () => {
    render(<PagePager label="Pagination" page={6} totalPages={20} hrefFor={(p) => `?page=${p}`} />);
    expect(screen.getAllByText("…").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "20" })).toBeInTheDocument();
  });

  it("emits button-mode page changes and disables edges at bounds", async () => {
    const onPage = vi.fn();
    render(
      <PagePager
        label="Pagination"
        page={1}
        totalPages={3}
        controls={controls}
        onPage={onPage}
        summary={<span>1–10 of 25</span>}
      />,
    );
    expect(screen.getByText("1–10 of 25")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous page" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPage).toHaveBeenCalledWith(2);
    await userEvent.click(screen.getByRole("button", { name: "Page 3" }));
    expect(onPage).toHaveBeenCalledWith(3);
  });
});
