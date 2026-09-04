import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CatalogQueryField } from "@/components/molecules/catalog-query-field";

describe("CatalogQueryField", () => {
  it("autocompletes reserved words and applies a typo correction", async () => {
    const user = userEvent.setup();
    render(
      <CatalogQueryField
        label="Search"
        placeholder="Query"
        submitLabel="Apply"
        defaultValue=""
        correctionLabel="Did you mean"
        fieldsLabel="Fields"
        operatorsLabel="Operators"
        literalHint={'Quotes search a reserved word as text: "AND".'}
      />,
    );

    const input = screen.getByRole("combobox", { name: "Search" });
    await user.type(input, "TA");
    expect(screen.getByRole("option", { name: "TAGS Fields" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "TAGS Fields" }));
    expect(input).toHaveValue("TAGS");
    expect(screen.getByRole("option", { name: /^:/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "IN Operators" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "AND Operators" })).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "harnes:codex");
    await user.click(screen.getByRole("button", { name: /Did you mean/ }));
    expect(input).toHaveValue("HARNESS:codex");

    await user.clear(input);
    await user.type(input, "author tags");
    expect(screen.queryByRole("button", { name: /Did you mean/ })).toBeNull();
  });
});
