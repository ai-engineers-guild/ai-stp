import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";

describe("SearchableMultiSelect", () => {
  it("renders repeated form-native values and selected count", async () => {
    const user = userEvent.setup();
    render(
      <SearchableMultiSelect
        name="tag"
        label="Tags"
        searchLabel="Search tags"
        options={["python", "security", "TypeScript"]}
        selected={["security"]}
        form="catalog-form"
      />,
    );

    expect(screen.getByText("Tags (1)")).toBeInTheDocument();
    expect(screen.getByText("Tags (1)").closest("details")).toHaveClass("min-w-0");
    expect(screen.getByRole("checkbox", { name: "security" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "security" })).toHaveAttribute(
      "form",
      "catalog-form",
    );
    await user.type(screen.getByRole("searchbox", { name: "Search tags" }), "TYPE");
    expect(screen.getByRole("checkbox", { name: "TypeScript" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "python" })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "security" })).toBeNull();
  });

  it("shows every option after clearing the case-insensitive search", async () => {
    const user = userEvent.setup();
    render(
      <SearchableMultiSelect
        name="harness_id"
        label="Harness"
        searchLabel="Search harnesses"
        options={["codex", "claude-code"]}
        selected={[]}
      />,
    );

    const search = screen.getByRole("searchbox", { name: "Search harnesses" });
    await user.type(search, "CODEX");
    expect(screen.getByRole("checkbox", { name: "codex" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "claude-code" })).toBeNull();
    await user.clear(search);
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  });

  it("toggles object options through onChange", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SearchableMultiSelect
        name="authors"
        label="Authors"
        searchLabel="Search authors"
        options={[
          { value: "account_a", label: "Ada" },
          { value: "account_b", label: "Bea" },
        ]}
        selected={["account_a"]}
        onChange={onChange}
      />,
    );
    await user.click(screen.getByRole("checkbox", { name: "Ada" }));
    expect(onChange).toHaveBeenCalledWith([]);
    await user.click(screen.getByRole("checkbox", { name: "Bea" }));
    expect(onChange).toHaveBeenLastCalledWith(["account_b"]);
  });
});
