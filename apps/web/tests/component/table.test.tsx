import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";

describe("Table atoms", () => {
  it("renders an accessible table with scoped header cells", () => {
    render(
      <Table>
        <THead>
          <Tr>
            <Th>Name</Th>
            <Th>Status</Th>
          </Tr>
        </THead>
        <TBody>
          <Tr>
            <Td>Alice</Td>
            <Td>Active</Td>
          </Tr>
        </TBody>
      </Table>,
    );
    expect(screen.getByRole("table")).toHaveAttribute("data-ui", "ui-table");
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Alice" })).toBeInTheDocument();
  });

  it("owns head/cell styling while merging layout classes", () => {
    render(
      <Table>
        <THead>
          <Tr>
            <Th className="w-11">Pick</Th>
          </Tr>
        </THead>
        <TBody>
          <Tr>
            <Td className="max-w-64">Value</Td>
          </Tr>
        </TBody>
      </Table>,
    );
    const th = screen.getByRole("columnheader", { name: "Pick" });
    expect(th.className).toMatch(/text-muted-foreground/);
    expect(th.className).toMatch(/w-11/);
    const td = screen.getByRole("cell", { name: "Value" });
    expect(td.className).toMatch(/px-3/);
    expect(td.className).toMatch(/max-w-64/);
  });
});
