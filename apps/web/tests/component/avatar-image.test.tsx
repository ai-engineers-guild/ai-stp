import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AvatarImage } from "@/components/atoms/avatar-image";

describe("AvatarImage", () => {
  it("replaces an unavailable image with the supplied fallback", () => {
    const { container } = render(
      <AvatarImage src="/missing-avatar.jpg" className="avatar" fallback={<span>AL</span>} />,
    );

    const image = container.querySelector("img");
    expect(image).not.toBeNull();
    if (!image) throw new Error("expected avatar image");
    fireEvent.error(image);

    expect(container.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByText("AL")).toBeVisible();
  });

  it("shows the fallback when no avatar URL exists", () => {
    render(<AvatarImage src={null} className="avatar" fallback={<span>AL</span>} />);

    expect(screen.getByText("AL")).toBeVisible();
  });
});
