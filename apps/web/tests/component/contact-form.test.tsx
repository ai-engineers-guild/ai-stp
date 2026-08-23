import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";

vi.mock("@/lib/actions/complaints", () => ({
  submitComplaint: vi.fn().mockResolvedValue({
    schema_version: 1,
    complaint_id: "complaint_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    accepted: true,
  }),
}));

const { ContactForm } = await import("@/components/organisms/contact-form");
const { submitComplaint } = await import("@/lib/actions/complaints");

describe("ContactForm", () => {
  it("submits a complaint through the API and never shows the mail warning", async () => {
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <ContactForm targetKind="component" target="component_example@1.0" />
      </NextIntlClientProvider>,
    );
    expect(screen.queryByText(/Mail is not configured/i)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Reply email"), "ada@example.com");
    await user.type(screen.getByLabelText("Subject"), "broken skill");
    await user.type(
      screen.getByLabelText("Message"),
      "The published skill fails its documented install path.",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(submitComplaint).toHaveBeenCalledWith({
      targetKind: "component",
      target: "component_example@1.0",
      senderName: "Ada",
      replyEmail: "ada@example.com",
      subject: "broken skill",
      message: "The published skill fails its documented install path.",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("The complaint was accepted.");
    expect(screen.queryByText(/Mail is not configured/i)).not.toBeInTheDocument();
  });
});
