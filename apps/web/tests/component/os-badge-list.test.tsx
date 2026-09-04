import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OsBadgeList } from "@/components/molecules/os-badge-list";
import {
  namedHarnesses,
  namedOperatingSystems,
  namedPassportHarnesses,
  namedProjectionKinds,
} from "@/lib/catalog-harnesses";

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
    expect(namedPassportHarnesses({ harness_id: "claude-code" })).toEqual(["claude-code"]);
    expect(
      namedPassportHarnesses({
        harness_id: "claude-code",
        harness_ids: ["claude-code", "codex"],
      }),
    ).toEqual(["claude-code", "codex"]);
    expect(namedOperatingSystems({ supported_os: ["linux", "windows"] })).toEqual([
      "linux",
      "windows",
    ]);
    expect(namedOperatingSystems({})).toEqual([]);
    expect(
      namedPassportHarnesses({
        origin_harness_id: "claude-code",
        adaptations: [{ harness_id: "claude-code" }, { harness_id: "codex" }],
      }),
    ).toEqual(["claude-code", "codex"]);
    expect(
      namedOperatingSystems({
        adaptations: [
          {
            scope_adaptations: [
              { supported_os: ["linux", "macos"] },
              { supported_os: ["windows"] },
            ],
          },
        ],
      }),
    ).toEqual(["linux", "macos", "windows"]);
    expect(
      namedProjectionKinds({
        adaptations: [
          {
            scope_adaptations: [
              { projection_kind: "native_files" },
              { projection_kind: "native_files" },
            ],
          },
        ],
      }),
    ).toEqual(["native_files"]);
  });

  it("treats a missing operating-system list as empty rather than crashing", () => {
    render(<OsBadgeList empty="None listed" />);
    expect(screen.getByText("None listed")).toBeVisible();
  });
});
