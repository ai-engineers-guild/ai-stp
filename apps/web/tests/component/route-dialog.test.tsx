import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/en.json";
import { RouteDialog } from "@/components/molecules/route-dialog";
const { back } = vi.hoisted(() => ({ back: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back }) }));
it("shows the route content as an accessible dialog and closes through browser history", async () => {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <RouteDialog title="Add project">
        <p>Project fields</p>
      </RouteDialog>
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("dialog", { name: "Add project" })).toBeVisible();
  expect(screen.getByText("Project fields")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: messages.corporate.close }));
  expect(back).toHaveBeenCalledTimes(1);
});
