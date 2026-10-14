import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { expect, it } from "vitest";
import messages from "../../messages/en.json";
import { InstallBlock } from "@/components/organisms/install-block";
import { CLI_RELEASES_URL } from "@/lib/cli-copy";

it("offers the native release and states the platform installation boundary", () => {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <InstallBlock />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("link", { name: "Download CLI" }).getAttribute("href")).toBe(
    CLI_RELEASES_URL,
  );
  expect(screen.getByText(/Linux supports provider installation/)).toBeTruthy();
});
