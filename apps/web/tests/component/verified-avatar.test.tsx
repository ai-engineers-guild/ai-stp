import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VerifiedAvatar } from "@/components/molecules/verified-avatar";

describe("VerifiedAvatar", () => {
  it("shows a compact adjacent verification marker and a bordered avatar", () => {
    const { container } = render(
      <VerifiedAvatar
        src={null}
        verified
        verifiedLabel="Author identity verified"
        fallback="AL"
        size="lg"
      />,
    );

    const marker = screen.getByLabelText("Author identity verified");
    expect(marker).toHaveClass("bottom-0", "left-0", "border-2");
    expect(screen.getByText("AL")).toHaveClass("border", "rounded-full");
    expect(container.firstElementChild).not.toHaveClass("ring-primary");
    expect(container.firstElementChild).toHaveStyle({ width: "68px", height: "68px" });
  });

  it("does not render a verification marker for an unverified author", () => {
    render(<VerifiedAvatar src={null} verified={false} verifiedLabel="Verified" />);
    expect(screen.queryByLabelText("Verified")).not.toBeInTheDocument();
  });

  it("keeps the same row box for photo and placeholder variants", () => {
    const { rerender, container } = render(
      <VerifiedAvatar
        src="https://example.test/avatar.png"
        verified
        verifiedLabel="Verified"
        size="sm"
      />,
    );
    expect(container.firstElementChild).toHaveStyle({ width: "24px", height: "24px" });
    expect(container.querySelector("img")).toHaveClass("rounded-full", "border");
    expect(container.querySelector("img")).toHaveAttribute("width", "24");
    rerender(
      <VerifiedAvatar
        src={null}
        verified={false}
        verifiedLabel="Verified"
        size="sm"
        fallback="AB"
      />,
    );
    expect(container.firstElementChild).toHaveStyle({ width: "24px", height: "24px" });
    expect(screen.queryByLabelText("Verified")).not.toBeInTheDocument();
    expect(screen.getByText("AB")).toHaveClass("rounded-full", "border");
  });
});
