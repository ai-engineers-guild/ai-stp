import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreMeter } from "@/components/molecules/score-meter";

describe("ScoreMeter", () => {
  it("clamps percent below zero to the lower bound", () => {
    render(<ScoreMeter percent={-20} label="Safety" valueText="poor" />);

    const meter = screen.getByRole("meter", { name: "Safety" });
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
    expect(meter).toHaveAttribute("aria-valuenow", "0");
    expect(meter).toHaveAttribute("aria-valuetext", "poor");
    expect(meter).toHaveTextContent("0%");
    expect(meter.querySelector("[data-safety-fill]")).toHaveStyle({ width: "0%" });
  });

  it("clamps percent above one hundred to the upper bound", () => {
    render(<ScoreMeter percent={150} compact />);

    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveTextContent("100%");
    expect(meter.querySelector("[data-safety-fill]")).toHaveStyle({ width: "100%" });
  });

  it("keeps an in-range percent unclamped", () => {
    render(<ScoreMeter percent={64} />);

    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "64");
    expect(meter).toHaveTextContent("64%");
    expect(meter.querySelector("[data-safety-fill]")).toHaveStyle({ width: "64%" });
  });
});
