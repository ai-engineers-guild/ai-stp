import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const push = vi.fn();

vi.mock("@/lib/i18n/navigation", () => ({
  usePathname: () => "/catalog",
  useRouter: () => ({ push }),
}));

import { CatalogSearchForm } from "@/components/organisms/catalog-search-form";

describe("CatalogSearchForm", () => {
  it("omits empty controls from client navigation", () => {
    render(
      <CatalogSearchForm>
        <input aria-label="query" name="q" defaultValue="  " />
        <select aria-label="harness" name="harness_id" defaultValue="">
          <option value="">Any</option>
        </select>
        <textarea aria-label="author" name="author" defaultValue="" />
        <input aria-label="verified" type="checkbox" name="verified" value="1" />
        <input aria-label="resource" type="radio" name="resource" value="components" />
        <input aria-label="tag" name="tag" defaultValue="python" />
      </CatalogSearchForm>,
    );

    fireEvent.submit(screen.getByRole("search"));

    expect(push).toHaveBeenLastCalledWith("/catalog?tag=python&page=1", { scroll: false });
  });

  it("resets page to 1 and drops a stale cursor during client navigation", () => {
    render(
      <CatalogSearchForm>
        <input aria-label="query" name="q" defaultValue="NAME:tool" />
        <input name="cursor" defaultValue="stale-cursor" />
        <input name="page" defaultValue="4" />
      </CatalogSearchForm>,
    );

    fireEvent.submit(screen.getByRole("search"));

    expect(push).toHaveBeenLastCalledWith("/catalog?q=NAME%3Atool&page=1", { scroll: false });
    expect(push.mock.calls.at(-1)?.[0]).not.toContain("cursor=");
  });

  it("leaves an already-disabled control disabled", () => {
    render(
      <CatalogSearchForm id="catalog-form" className="filters">
        <input aria-label="disabled" name="ignored" defaultValue="value" disabled />
      </CatalogSearchForm>,
    );

    const form = screen.getByRole("search");
    expect(form).toHaveAttribute("id", "catalog-form");
    expect(form).toHaveClass("filters", "min-w-0");
    fireEvent.submit(form);
    expect(screen.getByLabelText("disabled")).toBeDisabled();
  });

  it("blocks an invalid structured query before navigation", () => {
    const reportValidity = vi
      .spyOn(HTMLInputElement.prototype, "reportValidity")
      .mockReturnValue(false);
    render(
      <CatalogSearchForm>
        <input aria-label="query" name="q" defaultValue="VERIFIED:MAYBE" />
      </CatalogSearchForm>,
    );

    const submitted = fireEvent.submit(screen.getByRole("search"));

    expect(submitted).toBe(false);
    expect(screen.getByLabelText("query")).toBeInvalid();
    expect(screen.getByLabelText("query")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("VERIFIED accepts true or false");
    expect(reportValidity).toHaveBeenCalledOnce();

    fireEvent.change(screen.getByLabelText("query"), {
      target: { value: "VERIFIED:true AND NAME:tool" },
    });
    expect(fireEvent.submit(screen.getByRole("search"))).toBe(false);
    expect(screen.getByLabelText("query")).toHaveAttribute("aria-invalid", "false");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(push).toHaveBeenCalled();
    reportValidity.mockRestore();
  });
});
