import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import { CliCopyBlock } from "@/components/molecules/cli-copy-block";

describe("CliCopyBlock", () => {
  it("copies with an icon button and keeps the documentation link", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });

    render(
      <CliCopyBlock
        command="ai-stp registry show component_demo@1.0"
        title="Use via CLI"
        copyLabel="Copy"
        copiedLabel="Copied"
        errorLabel="Copy failed"
        docsLabel="CLI documentation"
      />,
    );

    expect(screen.queryByRole("button", { name: "Copy" })).toBeVisible();
    expect(screen.getByRole("link", { name: "CLI documentation" })).toHaveAttribute(
      "href",
      "/docs",
    );
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("ai-stp registry show component_demo@1.0");
  });
});
