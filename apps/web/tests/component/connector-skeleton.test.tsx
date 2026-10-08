import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectorSkeleton } from "@/components/molecules/connector-skeleton";

describe("ConnectorSkeleton", () => {
  it("announces a busy loading region", () => {
    render(<ConnectorSkeleton label="Loading GitHub connector" />);
    expect(screen.getByRole("status", { name: "Loading GitHub connector" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });
});
