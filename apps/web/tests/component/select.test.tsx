import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Select } from "@/components/atoms/select";

describe("Select atom", () => {
  it("renders an accessible combobox and emits changes", async () => {
    const onChange = vi.fn();
    render(
      <Select aria-label="Team" onChange={onChange}>
        <option value="">All teams</option>
        <option value="ops">Operations</option>
      </Select>,
    );
    const select = screen.getByRole("combobox", { name: "Team" });
    await userEvent.selectOptions(select, "ops");
    expect(onChange).toHaveBeenCalled();
    expect(select).toHaveValue("ops");
  });

  it("applies the canonical control styling and merges className", () => {
    render(<Select aria-label="Pick" className="sm:w-auto" />);
    const select = screen.getByRole("combobox", { name: "Pick" });
    expect(select.className).toMatch(/h-11/);
    expect(select.className).toMatch(/rounded-sm/);
    expect(select.className).toMatch(/border-input/);
    expect(select.className).toMatch(/sm:w-auto/);
    expect(select).toHaveAttribute("data-ui", "ui-select");
  });
});
