import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../../messages/en.json";

const replace = vi.fn().mockResolvedValue({ ok: true });
const requestService = vi.fn().mockResolvedValue({ ok: true, caseId: "report_service" });
const requestCountry = vi.fn().mockResolvedValue({ ok: true, caseId: "report_country" });
vi.mock("@/actions/external-products", () => ({
  replaceExternalProductsAction: replace,
  requestExternalProductAction: requestService,
  requestCountryAction: requestCountry,
}));
const { ExternalProductManager } = await import("@/components/organisms/external-product-manager");

describe("ExternalProductManager", () => {
  it("attaches existing services and requests a shallow HTTPS service", async () => {
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <ExternalProductManager
          locale="en"
          objectKind="component"
          stableId="component_12345678"
          csrfToken="csrf"
          initialProducts={[
            {
              schema_version: 1,
              name: "Notion",
              canonical_domain: "notion.so",
              primary_url: "https://notion.so",
              country_codes: ["US"],
            },
          ]}
          selectedDomains={[]}
        />
      </NextIntlClientProvider>,
    );
    await user.click(screen.getByRole("checkbox", { name: /Notion/ }));
    await user.click(screen.getByRole("button", { name: "Save services" }));
    expect(replace).toHaveBeenCalledWith(
      expect.objectContaining({ canonicalDomains: ["notion.so"] }),
    );
    await user.type(screen.getByRole("textbox", { name: "Service name" }), "Kaspi");
    await user.type(
      screen.getByRole("textbox", { name: "Primary HTTPS URL" }),
      "https://kaspi.kz/shop",
    );
    await user.type(screen.getByRole("textbox", { name: "Country codes" }), "KZ");
    await user.type(screen.getByRole("textbox", { name: "Russian description" }), "Описание");
    await user.type(screen.getByRole("textbox", { name: "English description" }), "Description");
    await user.type(
      screen.getByRole("textbox", { name: "Description source HTTPS URL" }),
      "https://kaspi.kz/about",
    );
    await user.click(screen.getByRole("button", { name: "Request service" }));
    expect(requestService).toHaveBeenCalledWith(expect.objectContaining({ countryCodes: ["KZ"] }));
    expect(await screen.findByText(/Service request submitted/)).toBeVisible();
  });
});
