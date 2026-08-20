import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

import {
  PassportJsonViewer,
  publicPassportJson,
} from "@/components/molecules/passport-json-viewer";

describe("PassportJsonViewer", () => {
  it("pretty-prints public passport JSON and copies it", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const passport = { name: "demo", version: "1.0", license: { spdx_id: "MIT" } };

    render(
      <PassportJsonViewer
        value={passport}
        label="Public passport JSON"
        copyLabel="Copy passport JSON"
        copiedLabel="Copied"
      />,
    );

    expect(screen.getByText("Public passport JSON")).toBeVisible();
    expect(screen.getByText('"spdx_id"')).toBeVisible();
    expect(screen.getByText('"MIT"')).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Copy passport JSON" }));
    expect(writeText).toHaveBeenCalledWith(publicPassportJson(passport));
  });
});
