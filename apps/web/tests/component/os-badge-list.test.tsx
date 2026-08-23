import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OsBadgeList } from "@/components/molecules/os-badge-list";
import { namedHarnesses, namedOperatingSystems } from "@/lib/catalog-harnesses";

describe("compatibility lists", () => {
  it("renders every named operating system and falls back when the list is empty", () => {
    const { rerender } = render(
      <OsBadgeList values={["linux", "macos", "windows"]} empty="None listed" />,
    );
    expect(screen.getByText("linux")).toBeVisible();
    expect(screen.getByText("macos")).toBeVisible();
    expect(screen.getByText("windows")).toBeVisible();
    rerender(<OsBadgeList values={[]} empty="None listed" />);
    expect(screen.getByText("None listed")).toBeVisible();
  });

  it("reads every named harness and OS from the passport-shaped inputs", () => {
    expect(
      namedHarnesses({
        latest_harness_id: "claude-code",
        latest_harness_ids: ["claude-code", "codex"],
      }),
    ).toEqual(["claude-code", "codex"]);
    expect(namedHarnesses({ latest_harness_id: "pi", latest_harness_ids: [] })).toEqual(["pi"]);
    expect(namedOperatingSystems({ supported_os: ["linux", "windows"] })).toEqual([
      "linux",
      "windows",
    ]);
    expect(namedOperatingSystems({})).toEqual([]);
  });
});
