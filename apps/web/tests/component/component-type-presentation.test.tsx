import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComponentType } from "@/lib/api/generated/types.gen";
import { COMPONENT_TYPE_PRESENTATION, ComponentTypeIcon } from "@/theme/component-types";

describe("component type presentation registry (REQ-3418)", () => {
  it("covers every contract type with an icon and both locales", () => {
    for (const type of Object.values(ComponentType)) {
      const entry = COMPONENT_TYPE_PRESENTATION[type];
      expect(entry.labels.en).not.toBe("");
      expect(entry.labels.ru).not.toBe("");
      const { container, unmount } = render(<ComponentTypeIcon type={type} />);
      expect(container.querySelector("svg")).not.toBeNull();
      unmount();
    }
  });
});
